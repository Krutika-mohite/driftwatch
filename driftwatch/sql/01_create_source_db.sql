/*
  Driftwatch — Step 1: create the SOURCE database.

  This is the "old system" we are migrating data FROM.
  Run this once in SSMS or VS Code (mssql extension) connected to your local SQL Server.
  Safe to re-run: it drops and recreates the tables.
*/

IF DB_ID('DriftwatchSource') IS NULL
    CREATE DATABASE DriftwatchSource;
GO

USE DriftwatchSource;
GO

-- Drop in dependency order (orders depends on customers and products)
IF OBJECT_ID('dbo.orders', 'U') IS NOT NULL DROP TABLE dbo.orders;
IF OBJECT_ID('dbo.customers', 'U') IS NOT NULL DROP TABLE dbo.customers;
IF OBJECT_ID('dbo.products', 'U') IS NOT NULL DROP TABLE dbo.products;
GO

CREATE TABLE dbo.customers (
    customer_id   INT           NOT NULL PRIMARY KEY,
    full_name     NVARCHAR(100) NOT NULL,
    email         NVARCHAR(150) NULL,
    phone         VARCHAR(20)   NULL,
    city          NVARCHAR(60)  NULL,
    state         NVARCHAR(60)  NULL,
    signup_date   DATE          NOT NULL,
    is_active     BIT           NOT NULL DEFAULT 1
);

CREATE TABLE dbo.products (
    product_id    INT           NOT NULL PRIMARY KEY,
    product_name  NVARCHAR(120) NOT NULL,
    category      NVARCHAR(40)  NOT NULL,
    unit_price    DECIMAL(10,2) NOT NULL,
    created_at    DATETIME2     NOT NULL
);

CREATE TABLE dbo.orders (
    order_id      INT           NOT NULL PRIMARY KEY,
    customer_id   INT           NOT NULL REFERENCES dbo.customers(customer_id),
    product_id    INT           NOT NULL REFERENCES dbo.products(product_id),
    quantity      INT           NOT NULL,
    unit_price    DECIMAL(10,2) NOT NULL,
    discount_pct  DECIMAL(5,2)  NOT NULL DEFAULT 0,
    order_status  VARCHAR(20)   NOT NULL,   -- PLACED, SHIPPED, DELIVERED, CANCELLED, RETURNED
    order_date    DATETIME2     NOT NULL,
    updated_at    DATETIME2     NOT NULL
);

CREATE INDEX ix_orders_updated_at ON dbo.orders(updated_at);
GO

PRINT 'DriftwatchSource created. Next: run  python scripts/seed_source.py';
