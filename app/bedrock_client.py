import os
from anthropic import AsyncAnthropicBedrock
from typing import Optional

_bedrock_client: Optional[AsyncAnthropicBedrock] = None

def init_bedrock():
    global _bedrock_client
    if _bedrock_client is None:
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY")
        aws_secret_access_key = os.getenv("AWS_SECRET_KEY")
        aws_region = os.getenv("AWS_REGION", "ap-south-1")
        
        if aws_access_key_id and aws_secret_access_key:
            _bedrock_client = AsyncAnthropicBedrock(
                aws_region=aws_region,
                aws_access_key=aws_access_key_id,
                aws_secret_key=aws_secret_access_key
            )
        else:
            _bedrock_client = AsyncAnthropicBedrock(
                aws_region=aws_region
            )

async def close_bedrock():
    global _bedrock_client
    if _bedrock_client is not None:
        await _bedrock_client.close()
        _bedrock_client = None

def get_bedrock_client() -> AsyncAnthropicBedrock:
    global _bedrock_client
    if _bedrock_client is None:
        init_bedrock()
    return _bedrock_client
