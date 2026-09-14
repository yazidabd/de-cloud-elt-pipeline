output "warehouse_name" {
  value = snowflake_warehouse.elt_wh.name
}

output "database_name" {
  value = snowflake_database.elt_db.name
}

output "raw_schema_name" {
  value = snowflake_schema.raw_schema.name
}

output "raw_stage_name" {
  value = snowflake_stage.raw_stage.name
}

output "role_name" {
  value = snowflake_account_role.loader_role.name
}
