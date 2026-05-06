import boto3
from botocore.client import Config
from .context import AgentContext
import os

class S3Client:
    def __init__(self, context: AgentContext):
        self.context = context
        self.s3 = boto3.client(
            's3',
            endpoint_url=self.context.s3_endpoint,
            aws_access_key_id=self.context.s3_access_key,
            aws_secret_access_key=self.context.s3_secret_key,
            config=Config(signature_version='s3v4'),
            region_name='us-east-1' # Default for MinIO
        )

    def download_directory(self, thread_id: str, sub_path: str, local_dir: str):
        prefix = f"tasks/{thread_id}/{sub_path}"
        paginator = self.s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.context.s3_bucket, Prefix=prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    rel_path = os.path.relpath(key, prefix)
                    dest_path = os.path.join(local_dir, rel_path)
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    self.s3.download_file(self.context.s3_bucket, key, dest_path)

    def upload_file(self, thread_id: str, local_path: str):
        filename = os.path.basename(local_path)
        key = f"tasks/{thread_id}/output/{filename}"
        self.s3.upload_file(local_path, self.context.s3_bucket, key)
