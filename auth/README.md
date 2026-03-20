# Auth

> **Status: Planned**

Centralized access control layer for internal services. Rather than exposing services publicly or managing access per-app, this will act as a single gate — I decide who gets in, and everything else stays private by default.

## What it will do

- OAuth-based authentication so approved users can log in with an existing identity (Google, GitHub, etc.) rather than managing separate credentials
- Per-service authorization — access to the ML platform, resume builder, or any future internal tool is granted explicitly, not by default
- Sits in front of any service that shouldn't be public, handling auth before the request ever reaches the app

## Why

Right now internal services are protected by Cloudflare Access, which works but ties access control to Cloudflare's dashboard. This will bring that logic into the cluster and make it manageable as code alongside everything else.
