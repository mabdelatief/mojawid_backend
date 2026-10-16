"""The analysis worker: a small HTTP service around the GPU pipeline. In dev it runs on this
laptop's GPU; in production inside a Modal Server (docs/architecture.md). Only the API calls it.
"""
