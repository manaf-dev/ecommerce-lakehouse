-- ============================================================
-- E-Commerce Lakehouse — Athena Sample Queries
-- Database: lakehouse_dwh (Glue Data Catalog)
-- Tables:   products, orders, order_items  (Delta Lake)
-- ============================================================

-- Monthly order summary (partition-pruned)
SELECT
    order_month,
    COUNT(DISTINCT order_id) AS orders,
    SUM(total_amount)        AS revenue
FROM lakehouse_dwh.orders
WHERE order_month = '2025-04'
GROUP BY order_month;

-- Top 10 products by order frequency
SELECT
    p.product_name,
    COUNT(*) AS frequency
FROM lakehouse_dwh.order_items oi
JOIN lakehouse_dwh.orders o
    ON oi.order_id = o.order_id
   AND oi.order_month = o.order_month
JOIN lakehouse_dwh.products p
    ON oi.product_id = p.product_id
WHERE oi.order_month = '2025-04'
GROUP BY p.product_name
ORDER BY frequency DESC
LIMIT 10;
