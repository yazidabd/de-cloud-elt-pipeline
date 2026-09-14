# variabel non-rahasia, aman dikomit ke git
# kredensial (account, user, private key) sengaja TIDAK didefinisikan di sini
# provider Snowflake otomatis baca dari env var SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER,
# SNOWFLAKE_PRIVATE_KEY_PATH, jadi gak ada secret yang perlu masuk file .tf atau .tfvars

variable "environment" {
  description = "Label environment, dipakai buat penamaan resource"
  type        = string
  default     = "dev"
}

variable "database_name" {
  description = "Nama database Snowflake buat project ini"
  type        = string
  default     = "ELT_PORTFOLIO"
}

variable "raw_schema_name" {
  description = "Schema tempat data mentah hasil load dari stage"
  type        = string
  default     = "RAW"
}

variable "role_name" {
  description = "Role custom yang dipakai loader/dbt, bukan pakai role default ACCOUNTADMIN"
  type        = string
  default     = "ELT_LOADER_ROLE"
}

variable "warehouse_size" {
  description = "Ukuran warehouse, XSMALL cukup buat portfolio dan paling murah"
  type        = string
  default     = "XSMALL"
}

variable "auto_suspend_seconds" {
  description = "Warehouse auto-suspend cepat biar gak boros credit trial saat idle"
  type        = number
  default     = 60
}

variable "admin_role" {
  description = "Role dengan privilege cukup buat provisioning, dipakai cuma saat terraform apply"
  type        = string
  default     = "SYSADMIN"
}

variable "private_key_path" {
  description = "Path ke file private key Snowflake (isi file-nya tetap gitignored, ini cuma nyimpen lokasinya)"
  type        = string
  default     = "../secrets/rsa_key.p8"
}
