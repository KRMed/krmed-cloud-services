# ML Platform

> **Status: Planned**

A self-hosted ML fine-tuning pipeline running on the cluster. The goal is a managed environment for submitting fine-tuning jobs against base models — think what cloud providers offer, but running on my own hardware with no per-hour billing.

## What it will do

- Submit and manage fine-tuning jobs through a simple interface
- Track experiments, runs, and model versions
- Store and serve fine-tuned model artifacts
- Integrate with the auth layer so access is gated to approved users

## Why

Cloud ML platforms charge significantly for GPU time and data egress. Running this on-cluster keeps costs flat and keeps data local.
