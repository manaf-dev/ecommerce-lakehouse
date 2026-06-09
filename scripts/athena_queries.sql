-- ============================================================
-- E-Commerce Lakehouse — Athena Sample Queries
-- Database: ecommerce-lakehouse (Glue Data Catalog)
-- Tables:   products, orders, order_items  (Delta Lake via Glue Crawler)
-- ============================================================
-- All queries are partition-pruned on order_month so Athena
-- scans only the relevant partition rather than the full table.
-- Replace '2025-04' with the target month in YYYY-MM format.
-- ============================================================


-- ── Query 1: Monthly order summary ──────────────────────────────────────────
-- Partition pruning: WHERE order_month = '...' limits the S3 scan
-- to a single partition directory (orders/order_month=2025-04/).
-- Without this predicate Athena would full-scan the orders table.

SELECT
    order_month,
    COUNT(DISTINCT order_id)  AS orders,
    SUM(total_amount)         AS revenue
FROM orders
WHERE order_month = '2025-04'       -- partition-pruning predicate
GROUP BY order_month;


-- ── Query 2: Top 10 products by order frequency ──────────────────────────────
-- Join locality: the order_month predicate is pushed to BOTH
-- order_items and orders partitions.  By joining on both
-- oi.order_month = o.order_month AND oi.order_id = o.order_id
-- Athena prunes to matching partition directories in both tables,
-- minimising data scanned and avoiding cross-partition shuffle.

SELECT
    p.product_name,
    COUNT(*)  AS frequency
FROM order_items  oi
JOIN orders       o  ON  oi.order_id    = o.order_id
                     AND oi.order_month = o.order_month  -- join locality
JOIN products     p  ON  oi.product_id  = p.product_id
WHERE oi.order_month = '2025-04'                         -- partition-pruning predicate
GROUP BY p.product_name
ORDER BY frequency DESC
LIMIT 10;
