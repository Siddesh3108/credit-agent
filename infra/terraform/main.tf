# SCAFFOLD ONLY -- never applied, never run through `terraform validate`.
# This sandbox has no network access to releases.hashicorp.com to install
# the terraform binary at all, let alone AWS credentials to apply this
# against. Syntax is written carefully but treat this as a starting
# point to review line-by-line, not a verified artifact.
#
# Cloud examples lean AWS-flavored per the design doc's own assumption
# (§19.1): "every pattern here maps to equivalent GCP/Azure services."

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "environment" {
  type    = string
  default = "dev"
}

resource "aws_db_instance" "audit_postgres" {
  identifier              = "card-servicing-audit-${var.environment}"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = "db.r6g.large"
  allocated_storage       = 100
  storage_encrypted       = true
  multi_az                = true # §12.3: RPO target of minutes for the audit store
  backup_retention_period = 35
  deletion_protection     = true
  # Master credentials should come from a secrets manager reference, not
  # a literal here -- intentionally left as a TODO rather than a fake
  # placeholder that looks configured.
}

resource "aws_kms_key" "field_level_encryption" {
  description             = "Tier 1 field-level encryption key (design doc §10.2)"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_secretsmanager_secret" "anthropic_api_key" {
  name = "card-servicing/${var.environment}/anthropic-api-key"
}

# Segmented networks (§10.8): conversational tier is internet-facing,
# core banking never is. Left as a TODO block rather than fabricated
# VPC/subnet resources, since the actual topology depends entirely on
# your existing core banking network, which this repo has no visibility
# into.
# resource "aws_vpc" "conversational_tier" { ... }
# resource "aws_vpc" "core_banking_tier"   { ... }  # not internet-facing
