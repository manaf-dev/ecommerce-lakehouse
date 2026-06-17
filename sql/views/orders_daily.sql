CREATE OR REPLACE VIEW orders_daily AS
SELECT
    date                             AS order_date,
    COUNT(DISTINCT order_id)         AS order_count,
    COUNT(DISTINCT user_id)          AS unique_customers,
    ROUND(SUM(total_amount), 2)      AS daily_revenue,
    ROUND(AVG(total_amount), 2)      AS avg_order_value
FROM orders
GROUP BY date
ORDER BY date
