"""Shared Garage (S3) client construction.

Garage requires path-style addressing (it does not support virtual-host-style
bucket addressing) and ignores the region, though botocore still requires one to
be set. Both the checkpoint upload and the dataset download build their client
the same way, so the construction lives here in one place.
"""

import boto3
from botocore.config import Config as BotoConfig

from crucible_worker import config

# Garage ignores the region, but botocore requires one to be set.
GARAGE_REGION = "garage"


def build_client(cfg: config.Config):
    """Build a path-style S3 client pointed at the configured Garage endpoint."""
    return boto3.client(
        "s3",
        endpoint_url=cfg.garage_endpoint,
        aws_access_key_id=cfg.garage_access_key,
        aws_secret_access_key=cfg.garage_secret_key,
        region_name=GARAGE_REGION,
        config=BotoConfig(s3={"addressing_style": "path"}),
    )
