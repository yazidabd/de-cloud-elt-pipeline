from datetime import datetime

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

PROJECT_ROOT = "/home/tupay/PROJECT/de-cloud-elt-pipeline"

# path venv tiap komponen, sengaja gak dijadiin satu venv gede
# biar dependency tiap komponen tetap terisolasi (sesuai keputusan awal)
EXTRACTOR_PYTHON = f"{PROJECT_ROOT}/extractor/venv/bin/python"
LOADER_PYTHON = f"{PROJECT_ROOT}/loader/venv/bin/python"
DBT_BIN = f"{PROJECT_ROOT}/dbt_project/venv/bin/dbt"
REVERSE_ETL_PYTHON = f"{PROJECT_ROOT}/reverse_etl/venv/bin/python"

default_args = {
    "owner": "yazid",
    "retries": 2,
    "retry_delay": 300,
}

with DAG(
    dag_id="cloud_elt_dag",
    description="Batch ELT: extract FakeStoreAPI (products) + synthetic orders -> Snowflake -> dbt -> Airtable",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime(2026, 9, 1),
    catchup=False,
    tags=["portfolio", "cloud-elt", "snowflake"],
) as dag:

    extract_products = BashOperator(
        task_id="extract_products",
        bash_command=f"cd {PROJECT_ROOT}/extractor && {EXTRACTOR_PYTHON} extract_products.py",
    )

    extract_orders = BashOperator(
        task_id="extract_orders",
        bash_command=f"cd {PROJECT_ROOT}/extractor && {EXTRACTOR_PYTHON} extract_orders.py",
    )

    load_to_snowflake = BashOperator(
        task_id="load_to_snowflake",
        bash_command=f"cd {PROJECT_ROOT}/loader && {LOADER_PYTHON} load_to_snowflake.py",
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {PROJECT_ROOT}/dbt_project && {DBT_BIN} run",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {PROJECT_ROOT}/dbt_project && {DBT_BIN} test",
    )

    reverse_etl_push = BashOperator(
        task_id="reverse_etl_push",
        bash_command=f"cd {PROJECT_ROOT}/reverse_etl && {REVERSE_ETL_PYTHON} push_to_airtable.py",
    )

    [extract_products, extract_orders] >> load_to_snowflake >> dbt_run >> dbt_test >> reverse_etl_push
