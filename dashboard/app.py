import os

import pandas as pd
import plotly.express as px
import snowflake.connector
import streamlit as st
from cryptography.hazmat.primitives import serialization

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
PRIVATE_KEY_PATH = os.path.join(PROJECT_ROOT, "secrets", "rsa_key.p8")

DATABASE = "ELT_PORTFOLIO"
SCHEMA = "STAGING_MARTS"
WAREHOUSE = "ELT_PORTFOLIO_WH"
ROLE = "ELT_LOADER_ROLE"


# baca private key terenkripsi, konsisten sama cara auth di loader dan reverse_etl
def load_private_key():
    passphrase = os.environ["SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"]
    with open(PRIVATE_KEY_PATH, "rb") as key_file:
        p_key = serialization.load_pem_private_key(
            key_file.read(),
            password=passphrase.encode(),
        )
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


# cache koneksi biar gak connect ulang tiap kali user interaksi sama widget Streamlit
@st.cache_resource
def get_connection():
    account = f"{os.environ['SNOWFLAKE_ORGANIZATION_NAME']}-{os.environ['SNOWFLAKE_ACCOUNT_NAME']}"
    return snowflake.connector.connect(
        account=account,
        user=os.environ["SNOWFLAKE_USER"],
        private_key=load_private_key(),
        warehouse=WAREHOUSE,
        database=DATABASE,
        schema=SCHEMA,
        role=ROLE,
    )


# cache hasil query 5 menit, biar gak nge-hit Snowflake tiap kali widget di-refresh
@st.cache_data(ttl=300)
def run_query(query):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query)
    columns = [col[0].lower() for col in cursor.description]
    rows = cursor.fetchall()
    cursor.close()
    return pd.DataFrame(rows, columns=columns)


def load_fact_order_items():
    return run_query("""
        SELECT
            f.order_id, f.product_id, f.date_key, f.quantity,
            f.unit_price, f.line_total, f.discount_percentage, f.line_discounted_total,
            p.title, p.category, p.rating_rate, p.rating_count
        FROM fact_order_items f
        LEFT JOIN dim_product p ON f.product_id = p.product_id
    """)


def load_daily_summary():
    return run_query("""
        SELECT date_key, total_orders, total_quantity, total_revenue, total_discounted_revenue
        FROM agg_daily_sales_summary
        ORDER BY date_key
    """)


def render_kpi_row(fact_df, daily_df):
    total_revenue = fact_df["line_total"].sum()
    total_orders = fact_df["order_id"].nunique()
    total_items_sold = fact_df["quantity"].sum()
    avg_discount = fact_df["discount_percentage"].mean()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Revenue", f"${total_revenue:,.2f}")
    col2.metric("Total Orders", f"{total_orders:,}")
    col3.metric("Items Sold", f"{total_items_sold:,}")
    col4.metric("Avg Discount", f"{avg_discount:.1f}%")


def render_revenue_by_category(fact_df):
    st.subheader("Revenue by Category")
    revenue_by_category = (
        fact_df.groupby("category")["line_total"].sum().reset_index().sort_values("line_total", ascending=False)
    )
    fig = px.bar(revenue_by_category, x="category", y="line_total", labels={"line_total": "Revenue ($)"})
    st.plotly_chart(fig, use_container_width=True)


def render_top_products(fact_df):
    st.subheader("Top 10 Products by Quantity Sold")
    top_products = (
        fact_df.groupby("title")["quantity"].sum().reset_index().sort_values("quantity", ascending=False).head(10)
    )
    fig = px.bar(top_products, x="quantity", y="title", orientation="h")
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)


def render_price_vs_rating(fact_df):
    st.subheader("Price vs Rating (per product)")
    product_level = fact_df.drop_duplicates(subset="product_id")
    fig = px.scatter(
        product_level, x="rating_rate", y="unit_price", size="rating_count",
        hover_data=["title"], labels={"rating_rate": "Rating", "unit_price": "Price ($)"},
    )
    st.plotly_chart(fig, use_container_width=True)


def render_daily_trend(daily_df):
    st.subheader("Daily Revenue Trend")
    if len(daily_df) < 2:
        st.info("Baru ada data dari 1 hari pipeline berjalan. Chart tren bakal makin bermakna seiring pipeline dijalankan rutin tiap hari.")
    fig = px.line(daily_df, x="date_key", y="total_revenue", markers=True)
    st.plotly_chart(fig, use_container_width=True)


def main():
    st.set_page_config(page_title="Cloud ELT Sales Dashboard", layout="wide")
    st.title("E-Commerce Sales Dashboard")
    st.caption("Data dari FakeStoreAPI (katalog produk) dan order sintetis (Faker), diproses lewat Snowflake + dbt")

    fact_df = load_fact_order_items()
    daily_df = load_daily_summary()

    render_kpi_row(fact_df, daily_df)
    st.divider()

    col_left, col_right = st.columns(2)
    with col_left:
        render_revenue_by_category(fact_df)
    with col_right:
        render_top_products(fact_df)

    render_price_vs_rating(fact_df)
    render_daily_trend(daily_df)


if __name__ == "__main__":
    main()
