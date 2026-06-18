terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project_id" {
  type        = string
  description = "Google Cloud project that owns the optional mutation burst."
}

variable "billing_account_id" {
  type        = string
  description = "Billing account that receives the slice 29 budget."
}

variable "budget_amount_eur" {
  type        = number
  default     = 20
  description = "Monthly budget amount for optional mutation bursts."
}

resource "google_pubsub_topic" "budget_notifications" {
  project = var.project_id
  name    = "xf-slice-29-budget-notifications"
}

resource "google_billing_budget" "mutation_burst" {
  billing_account = var.billing_account_id
  display_name    = "XF slice 29 mutation burst"

  amount {
    specified_amount {
      currency_code = "EUR"
      units         = var.budget_amount_eur
    }
  }

  threshold_rules {
    threshold_percent = 0.9
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  all_updates_rule {
    pubsub_topic = google_pubsub_topic.budget_notifications.id
  }
}
