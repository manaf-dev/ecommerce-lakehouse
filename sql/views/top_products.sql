CREATE OR REPLACE VIEW top_products AS
SELECT
    p.product_id,
    p.product_name,
    p.department,
    COUNT(oi.id)                AS times_ordered,
    COUNT(DISTINCT oi.order_id) AS distinct_orders,
    SUM(oi.reordered)           AS reorder_count,
    ROUND(
        CAST(SUM(oi.reordered) AS DOUBLE)
        / NULLIF(COUNT(oi.id), 0) * 100,
        1
    )                           AS reorder_rate_pct
FROM order_items oi
JOIN products p ON oi.product_id = CAST(p.product_id AS BIGINT)
GROUP BY p.product_id, p.product_name, p.department
ORDER BY times_ordered DESC
