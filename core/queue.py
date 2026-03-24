# Copyright 2026 AXLPROTOCOL INC.
# Licensed under the Apache License, Version 2.0
"""
AXL Silo — Queue Server

Manages concurrent LLM calls across multiple providers.
Rate limiting, retry logic, cost tracking, and priority routing.

The queue ensures:
1. No provider gets hammered beyond its rate limit
2. Failed calls get retried with exponential backoff
3. Local models (Ollama) get routed without API key
4. Cost per provider is tracked in real-time
5. The operator sees queue depth and latency per provider

This is NOT a simple sequential loop. It's a proper job queue
that can handle 4+ providers simultaneously.
"""

import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from collections import defaultdict
from queue import PriorityQueue

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""
    name: str                       # "openai", "anthropic", "google", "local"
    api_key: str = ""
    api_base: str = ""              # Custom base URL (Ollama, LiteLLM proxy)
    rate_limit_rpm: int = 60        # Requests per minute
    rate_limit_tpm: int = 100000    # Tokens per minute
    max_retries: int = 3
    retry_delay: float = 2.0        # Base delay (exponential backoff)
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0
    connection_type: str = "api"    # "api" or "ssh" for local tunneled models


# Default provider configurations
DEFAULT_PROVIDERS = {
    "anthropic": ProviderConfig(
        name="anthropic",
        rate_limit_rpm=50,
        rate_limit_tpm=80000,
        cost_per_input_token=3.0 / 1_000_000,
        cost_per_output_token=15.0 / 1_000_000,
    ),
    "openai": ProviderConfig(
        name="openai",
        rate_limit_rpm=60,
        rate_limit_tpm=150000,
        cost_per_input_token=2.5 / 1_000_000,
        cost_per_output_token=10.0 / 1_000_000,
    ),
    "google": ProviderConfig(
        name="google",
        rate_limit_rpm=60,
        rate_limit_tpm=120000,
        cost_per_input_token=1.25 / 1_000_000,
        cost_per_output_token=5.0 / 1_000_000,
    ),
    "local": ProviderConfig(
        name="local",
        rate_limit_rpm=999,
        rate_limit_tpm=999999,
        cost_per_input_token=0.0,
        cost_per_output_token=0.0,
        connection_type="api",  # Ollama uses HTTP API
    ),
}


@dataclass(order=True)
class Job:
    """A single LLM call job in the queue."""
    priority: int
    agent_name: str = field(compare=False)
    model: str = field(compare=False)
    provider: str = field(compare=False)
    system_prompt: str = field(compare=False)
    user_prompt: str = field(compare=False)
    callback: Optional[Callable] = field(compare=False, default=None)
    created_at: float = field(compare=False, default_factory=time.time)
    attempts: int = field(compare=False, default=0)
    job_id: int = field(compare=False, default=0)


class QueueServer:
    """
    Manages LLM calls across providers with rate limiting and cost tracking.
    
    Usage:
        queue = QueueServer()
        queue.register_provider("anthropic", api_key="sk-...")
        queue.register_provider("local", api_base="http://localhost:11434")
        queue.start()
        
        queue.submit(
            agent_name="Dr.Chen",
            model="anthropic/claude-sonnet-4-20250514",
            provider="anthropic",
            system_prompt=rosetta + agent_context,
            user_prompt=bus_state,
            callback=on_response,
        )
    """

    def __init__(self):
        self._queue = PriorityQueue()
        self._providers: Dict[str, ProviderConfig] = {}
        self._rate_windows: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._workers: Dict[str, threading.Thread] = {}
        self._running = False
        self._job_counter = 0

        # Tracking
        self._completed = 0
        self._failed = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._cost_by_provider: Dict[str, float] = defaultdict(float)
        self._latency_by_provider: Dict[str, List[float]] = defaultdict(list)

    def register_provider(self, name: str, api_key: str = "",
                          api_base: str = "", config: ProviderConfig = None):
        """Register a provider with its credentials."""
        if config:
            self._providers[name] = config
        elif name in DEFAULT_PROVIDERS:
            self._providers[name] = DEFAULT_PROVIDERS[name]
        else:
            self._providers[name] = ProviderConfig(name=name)

        # Override with provided credentials
        if api_key:
            self._providers[name].api_key = api_key
        if api_base:
            self._providers[name].api_base = api_base

        logger.info(f"Provider registered: {name} (RPM: {self._providers[name].rate_limit_rpm})")

    def start(self):
        """Start worker threads — one per registered provider."""
        self._running = True
        for name in self._providers:
            worker = threading.Thread(
                target=self._worker_loop,
                args=(name,),
                daemon=True,
                name=f"queue-worker-{name}"
            )
            self._workers[name] = worker
            worker.start()
            logger.info(f"Worker started: {name}")

    def stop(self):
        """Stop all workers."""
        self._running = False
        for worker in self._workers.values():
            worker.join(timeout=10)
        logger.info("Queue stopped")

    def submit(self, agent_name: str, model: str, provider: str,
               system_prompt: str, user_prompt: str,
               callback: Callable = None, priority: int = 5) -> int:
        """Submit a job to the queue. Returns job ID."""
        with self._lock:
            self._job_counter += 1
            job_id = self._job_counter

        job = Job(
            priority=priority,
            agent_name=agent_name,
            model=model,
            provider=provider,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            callback=callback,
            job_id=job_id,
        )
        self._queue.put(job)
        return job_id

    def stats(self) -> dict:
        """Queue statistics for the UI."""
        return {
            "queue_depth": self._queue.qsize(),
            "completed": self._completed,
            "failed": self._failed,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "cost_by_provider": dict(self._cost_by_provider),
            "total_cost": sum(self._cost_by_provider.values()),
            "avg_latency_by_provider": {
                name: round(sum(lats) / max(len(lats), 1), 2)
                for name, lats in self._latency_by_provider.items()
            },
            "providers": list(self._providers.keys()),
        }

    def _worker_loop(self, provider_name: str):
        """Worker loop for a single provider. Processes jobs from the queue."""
        while self._running:
            try:
                # Get next job (blocks for 1 second, then retries)
                try:
                    job = self._queue.get(timeout=1.0)
                except Exception:
                    continue

                # Skip if wrong provider
                if job.provider != provider_name:
                    self._queue.put(job)  # Put it back
                    time.sleep(0.1)
                    continue

                # Rate limiting
                self._wait_for_rate_limit(provider_name)

                # Execute the call
                result = self._execute_job(job)

                if result is not None:
                    self._completed += 1
                    if job.callback:
                        try:
                            job.callback(result)
                        except Exception as e:
                            logger.error(f"Callback error for {job.agent_name}: {e}")
                else:
                    # Retry logic
                    job.attempts += 1
                    provider = self._providers.get(provider_name)
                    max_retries = provider.max_retries if provider else 3

                    if job.attempts < max_retries:
                        delay = (provider.retry_delay if provider else 2.0) * (2 ** job.attempts)
                        logger.warning(f"Retrying {job.agent_name} in {delay}s (attempt {job.attempts})")
                        time.sleep(delay)
                        self._queue.put(job)
                    else:
                        logger.error(f"Job failed permanently: {job.agent_name} after {job.attempts} attempts")
                        self._failed += 1
                        if job.callback:
                            job.callback(None)

            except Exception as e:
                logger.error(f"Worker {provider_name} error: {e}")
                time.sleep(1)

    def _wait_for_rate_limit(self, provider_name: str):
        """Wait if we've exceeded the provider's rate limit."""
        provider = self._providers.get(provider_name)
        if not provider:
            return

        with self._lock:
            now = time.time()
            window = self._rate_windows[provider_name]

            # Clean old entries (older than 60 seconds)
            self._rate_windows[provider_name] = [t for t in window if now - t < 60]
            window = self._rate_windows[provider_name]

            if len(window) >= provider.rate_limit_rpm:
                # Wait until the oldest entry expires
                wait_time = 60 - (now - window[0]) + 0.1
                if wait_time > 0:
                    logger.info(f"Rate limit hit for {provider_name}. Waiting {wait_time:.1f}s")
                    time.sleep(wait_time)

            # Record this request
            self._rate_windows[provider_name].append(time.time())

    def _execute_job(self, job: Job) -> Optional[str]:
        """Execute a single LLM call. Returns the response text or None."""
        try:
            import litellm

            provider = self._providers.get(job.provider, ProviderConfig(name=job.provider))

            kwargs = {
                "model": job.model,
                "messages": [
                    {"role": "system", "content": job.system_prompt},
                    {"role": "user", "content": job.user_prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 200,
            }

            if provider.api_key:
                kwargs["api_key"] = provider.api_key
            if provider.api_base:
                kwargs["api_base"] = provider.api_base

            start = time.time()
            response = litellm.completion(**kwargs)
            latency = time.time() - start

            # Track metrics
            with self._lock:
                self._latency_by_provider[job.provider].append(latency)

                if hasattr(response, "usage") and response.usage:
                    input_tokens = getattr(response.usage, "prompt_tokens", 0)
                    output_tokens = getattr(response.usage, "completion_tokens", 0)
                    self._total_input_tokens += input_tokens
                    self._total_output_tokens += output_tokens

                    cost = (input_tokens * provider.cost_per_input_token +
                            output_tokens * provider.cost_per_output_token)
                    self._cost_by_provider[job.provider] += cost

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Job execution error for {job.agent_name}: {e}")
            return None
