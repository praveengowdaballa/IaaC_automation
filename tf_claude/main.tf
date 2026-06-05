terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-west-2"
}

locals {
  config = yamldecode(file("${path.module}/buckets.yaml"))

  buckets = {
    for bucket in local.config.buckets :
    bucket.name => bucket
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket = each.value.name

  tags = merge(
    {
      Environment = each.value.environment
    },
    each.value.tags
  )
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id

  versioning_configuration {
    status = each.value.versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_instance" "demo_vm" {
  ami           = "ami-0c02fb55956c7d316"
  instance_type = "t3.medium"

  tags = {
    Name = "terraform-ai-demo"
  }
}

resource "aws_instance" "demo_vmv1" {
  ami           = "ami-0c02fb55956c7d316"
  instance_type = "t3.medium"

  tags = {
    Name = "terraform-ai-demo"
  }
}
