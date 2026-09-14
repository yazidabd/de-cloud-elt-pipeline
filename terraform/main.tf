terraform {
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 0.94"
    }
  }
}

# provider sengaja gak diisi account/user/private_key eksplisit
# supaya wajib diambil dari environment variable, bukan hardcode di file
provider "snowflake" {
  authenticator = "JWT"
  private_key   = file(var.private_key_path)
  role          = var.admin_role
}

# warehouse terpisah dari warehouse default akun
# biar biaya compute project ini gampang dipantau sendiri, gak campur sama yang lain
resource "snowflake_warehouse" "elt_wh" {
  name                = "ELT_PORTFOLIO_WH"
  warehouse_size      = var.warehouse_size
  auto_suspend        = var.auto_suspend_seconds
  auto_resume         = true
  initially_suspended = true
}

resource "snowflake_database" "elt_db" {
  name    = var.database_name
  comment = "Database khusus portfolio project cloud ELT"
}

# schema RAW terpisah dari schema dbt (staging/marts)
# karena loader nulis ke sini, dbt yang nanti bikin schema turunannya sendiri
resource "snowflake_schema" "raw_schema" {
  database = snowflake_database.elt_db.name
  name     = var.raw_schema_name
}

# internal stage, jadi gak butuh cloud storage/akun lain sama sekali
# file dari extractor di-PUT ke sini dulu sebelum di-COPY INTO ke table raw
resource "snowflake_stage" "raw_stage" {
  name     = "RAW_LANDING_STAGE"
  database = snowflake_database.elt_db.name
  schema   = snowflake_schema.raw_schema.name
  comment  = "Landing zone internal buat file hasil extract sebelum di-load"
}

# role custom dengan privilege minimal, dipakai loader/dbt/CI
# bukan ACCOUNTADMIN, sesuai prinsip least privilege
resource "snowflake_account_role" "loader_role" {
  provider = snowflake.securityadmin
  name     = var.role_name
  comment  = "Role khusus buat proses ELT, cuma boleh akses database dan warehouse project ini"
}

resource "snowflake_grant_privileges_to_account_role" "warehouse_usage" {
  provider          = snowflake.securityadmin
  account_role_name = snowflake_account_role.loader_role.name
  privileges        = ["USAGE", "OPERATE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.elt_wh.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "database_usage" {
  provider          = snowflake.securityadmin
  account_role_name = snowflake_account_role.loader_role.name
  privileges        = ["USAGE", "CREATE SCHEMA"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.elt_db.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "raw_schema_privileges" {
  provider          = snowflake.securityadmin
  account_role_name = snowflake_account_role.loader_role.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE STAGE"]
  on_schema {
    schema_name = "\"${snowflake_database.elt_db.name}\".\"${snowflake_schema.raw_schema.name}\""
  }
}

# provider terpisah pakai role SECURITYADMIN, khusus buat resource yang ngatur role/grant
# karena SYSADMIN (dipakai buat warehouse/database/schema) secara default gak punya privilege CREATE ROLE
provider "snowflake" {
  alias         = "securityadmin"
  authenticator = "JWT"
  private_key   = file(var.private_key_path)
  role          = "SECURITYADMIN"
}

# assign role ke user, tanpa ini role cuma ada tapi gak ada yang bisa pakai
resource "snowflake_grant_account_role" "loader_role_to_user" {
  provider  = snowflake.securityadmin
  role_name = snowflake_account_role.loader_role.name
  user_name = "yaziduba"
}
