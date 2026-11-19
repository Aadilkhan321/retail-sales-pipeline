-- Star schema for the retail sales pipeline (MySQL 8 / InnoDB).
-- Generated from pipeline/db.py by `python -m pipeline.make_schema`.
-- The pipeline creates these tables itself; this file is for reading / manual use.

CREATE TABLE data_quality_issue (
	issue_id BIGINT NOT NULL, 
	rule VARCHAR(8) NOT NULL, 
	issue_type VARCHAR(40) NOT NULL, 
	action VARCHAR(12) NOT NULL, 
	source_sheet VARCHAR(40), 
	source_row INTEGER, 
	invoice_no VARCHAR(20), 
	stock_code VARCHAR(40), 
	detail VARCHAR(255), 
	PRIMARY KEY (issue_id)
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_dqi_rule ON data_quality_issue (rule);

CREATE TABLE dim_country (
	country_key INTEGER NOT NULL, 
	country_raw VARCHAR(60) NOT NULL, 
	country_name VARCHAR(60) NOT NULL, 
	region VARCHAR(60) NOT NULL, 
	PRIMARY KEY (country_key), 
	UNIQUE (country_raw)
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_dim_country_region ON dim_country (region);

CREATE TABLE dim_date (
	date_key INTEGER NOT NULL, 
	full_date DATE NOT NULL, 
	cal_year INTEGER NOT NULL, 
	cal_month INTEGER NOT NULL, 
	month_key VARCHAR(7) NOT NULL, 
	day_of_week INTEGER NOT NULL, 
	is_weekend BOOL NOT NULL, 
	PRIMARY KEY (date_key), 
	UNIQUE (full_date)
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_dim_date_month_key ON dim_date (month_key);

CREATE TABLE dim_product (
	product_key INTEGER NOT NULL, 
	stock_code VARCHAR(40) NOT NULL, 
	description VARCHAR(255), 
	is_non_product BOOL NOT NULL, 
	PRIMARY KEY (product_key), 
	UNIQUE (stock_code)
)ENGINE=InnoDB CHARSET=utf8mb4;


CREATE TABLE dim_customer (
	customer_key INTEGER NOT NULL, 
	customer_id VARCHAR(20) NOT NULL, 
	is_placeholder BOOL NOT NULL, 
	country_key INTEGER NOT NULL, 
	PRIMARY KEY (customer_key), 
	UNIQUE (customer_id), 
	FOREIGN KEY(country_key) REFERENCES dim_country (country_key)
)ENGINE=InnoDB CHARSET=utf8mb4;


CREATE TABLE fact_invoice_line (
	line_id BIGINT NOT NULL, 
	invoice_no VARCHAR(20) NOT NULL, 
	invoice_ts DATETIME NOT NULL, 
	date_key INTEGER NOT NULL, 
	customer_key INTEGER NOT NULL, 
	product_key INTEGER NOT NULL, 
	country_key INTEGER NOT NULL, 
	quantity INTEGER NOT NULL, 
	unit_price_gbp NUMERIC(14, 6) NOT NULL, 
	gross_gbp NUMERIC(20, 6) NOT NULL, 
	fx_rate NUMERIC(10, 6) NOT NULL, 
	fx_rate_date DATE NOT NULL, 
	gross_usd NUMERIC(24, 10) NOT NULL, 
	is_cancellation BOOL NOT NULL, 
	is_stock_writeoff BOOL NOT NULL, 
	is_non_product BOOL NOT NULL, 
	is_free_sample BOOL NOT NULL, 
	is_revenue BOOL NOT NULL, 
	source_sheet VARCHAR(40) NOT NULL, 
	source_row INTEGER NOT NULL, 
	PRIMARY KEY (line_id), 
	FOREIGN KEY(date_key) REFERENCES dim_date (date_key), 
	FOREIGN KEY(customer_key) REFERENCES dim_customer (customer_key), 
	FOREIGN KEY(product_key) REFERENCES dim_product (product_key), 
	FOREIGN KEY(country_key) REFERENCES dim_country (country_key)
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_fact_country ON fact_invoice_line (country_key);
CREATE INDEX ix_fact_customer ON fact_invoice_line (customer_key);
CREATE INDEX ix_fact_date ON fact_invoice_line (date_key);
CREATE INDEX ix_fact_invoice ON fact_invoice_line (invoice_no);
CREATE INDEX ix_fact_product_date ON fact_invoice_line (product_key, date_key);
CREATE UNIQUE INDEX ux_fact_source ON fact_invoice_line (source_sheet, source_row);
