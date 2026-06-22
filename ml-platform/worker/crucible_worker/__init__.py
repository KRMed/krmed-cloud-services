"""Crucible fine-tuning worker.

Pulls QLoRA fine-tune jobs from the Redis reliable queue, runs them on the GPU
node, and writes results back to Postgres and Garage. This package is the
GPU-independent core (queue consumer, job lifecycle, reconciler, validation,
guardrail); the QLoRA trainer is injected as an Executor (Phase 5C).
"""
