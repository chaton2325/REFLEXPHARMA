-- =====================================================
-- EXTENSIONS
-- =====================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- MODULES (IMPORTANT POUR RESPONSABILITES)
-- =====================================================
CREATE TABLE modules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,  -- stock, hr, accounting, sales, ai
    description TEXT
);

-- =====================================================
-- USERS
-- =====================================================
CREATE TABLE users (
    id SERIAL PRIMARY KEY,

    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(30),
    address TEXT,

    password_hash TEXT NOT NULL,

    profile_picture TEXT,
    language VARCHAR(10) DEFAULT 'fr',

    role VARCHAR(50) CHECK (
        role IN ('superadmin', 'admin', 'employee', 'cashier')
    ) NOT NULL,

    is_active BOOLEAN DEFAULT TRUE,

    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- SUPPLIERS
-- =====================================================
CREATE TABLE suppliers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    phone VARCHAR(50),
    email VARCHAR(150),
    address TEXT
);

-- =====================================================
-- PRODUCTS
-- =====================================================
CREATE TABLE products (
    id SERIAL PRIMARY KEY,

    -- =========================
    -- IDENTITÉ PRODUIT
    -- =========================
    name VARCHAR(255) NOT NULL,
    generic_name VARCHAR(255),
    description TEXT,

    category VARCHAR(100),

    -- =========================
    -- CODES BARRES
    -- =========================
    barcode_primary VARCHAR(120) UNIQUE,
    barcode_secondary VARCHAR(120),
    custom_qr TEXT,

    -- =========================
    -- UNITÉS (TRÈS IMPORTANT PHARMACIE)
    -- =========================
    base_unit VARCHAR(50) NOT NULL, 
    sub_unit VARCHAR(50), 

    -- ex:
    -- base_unit = "box"
    -- sub_unit = "tablet"

    unit_conversion_factor NUMERIC(12,4) DEFAULT 1,
    -- 1 box = 10 strips ou 1 strip = 10 tablets etc.

    -- =========================
    -- PRIX
    -- =========================
    purchase_price NUMERIC(12,2) DEFAULT 0,
    sale_price NUMERIC(12,2) DEFAULT 0,

    vat_rate NUMERIC(5,2) DEFAULT 0,

    -- =========================
    -- STOCK
    -- =========================
    stock_quantity NUMERIC(12,2) DEFAULT 0,
    min_stock_level NUMERIC(12,2) DEFAULT 0,
    max_stock_level NUMERIC(12,2),

    -- =========================
    -- LOT / EXPIRATION (CRITIQUE PHARMACIE)
    -- =========================
    batch_number VARCHAR(100),
    expiration_date DATE,

    -- =========================
    -- FOURNISSEUR
    -- =========================
    supplier_id INT REFERENCES suppliers(id),

    -- =========================
    -- TRAÇABILITÉ
    -- =========================
    location VARCHAR(100), -- shelf / warehouse / fridge

    is_prescription_required BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================
-- STOCK MOVEMENTS
-- =====================================================
CREATE TABLE stock_movements (
    id SERIAL PRIMARY KEY,
    product_id INT REFERENCES products(id) ON DELETE CASCADE,

    type VARCHAR(20) CHECK (type IN ('in','out','adjustment')),
    quantity INT NOT NULL,

    reason TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- ADMIN MODULE RESPONSIBILITIES (CORE FEATURE)
-- =====================================================
CREATE TABLE admin_module_assignments (
    id SERIAL PRIMARY KEY,

    admin_id INT REFERENCES users(id) ON DELETE CASCADE,
    module_id INT REFERENCES modules(id) ON DELETE CASCADE,

    can_read BOOLEAN DEFAULT TRUE,
    can_write BOOLEAN DEFAULT FALSE,
    can_delete BOOLEAN DEFAULT FALSE,
    can_manage BOOLEAN DEFAULT FALSE, -- full control module

    assigned_by INT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- EMPLOYEES
-- =====================================================
CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,

    national_id VARCHAR(50),
    phone VARCHAR(30),
    address TEXT,

    hire_date DATE,
    contract_type VARCHAR(50),

    base_salary NUMERIC(12,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active'
);

-- =====================================================
-- PAYROLL
-- =====================================================
CREATE TABLE payrolls (
    id SERIAL PRIMARY KEY,
    employee_id INT REFERENCES employees(id) ON DELETE CASCADE,

    month INT,
    year INT,

    base_salary NUMERIC(12,2),
    bonuses NUMERIC(12,2) DEFAULT 0,
    deductions NUMERIC(12,2) DEFAULT 0,

    net_salary NUMERIC(12,2),

    status VARCHAR(20) DEFAULT 'pending',
    payment_date DATE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);




-- =====================================================
-- PURCHASES
-- =====================================================
CREATE TABLE purchases (
    id SERIAL PRIMARY KEY,
    supplier_id INT REFERENCES suppliers(id),

    total_amount NUMERIC(12,2),
    vat_amount NUMERIC(12,2),

    status VARCHAR(50) DEFAULT 'pending',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE purchase_items (
    id SERIAL PRIMARY KEY,
    purchase_id INT REFERENCES purchases(id) ON DELETE CASCADE,
    product_id INT REFERENCES products(id),

    quantity INT,
    unit_price NUMERIC(12,2)
);

-- =====================================================
-- SALES
-- =====================================================
CREATE TABLE sales (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),

    total_amount NUMERIC(12,2),
    vat_amount NUMERIC(12,2),

    payment_method VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sale_items (
    id SERIAL PRIMARY KEY,
    sale_id INT REFERENCES sales(id) ON DELETE CASCADE,
    product_id INT REFERENCES products(id),

    quantity INT,
    unit_price NUMERIC(12,2)
);

-- =====================================================
-- ACCOUNTING
-- =====================================================
CREATE TABLE accounting_entries (
    id SERIAL PRIMARY KEY,

    type VARCHAR(20) CHECK (type IN ('income','expense')),

    amount NUMERIC(12,2),
    description TEXT,

    reference_type VARCHAR(50),
    reference_id INT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- TAXES (TVA)
-- =====================================================
CREATE TABLE tax_rates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50),
    rate NUMERIC(5,2)
);

-- =====================================================
-- MULTI LANGUAGE
-- =====================================================
CREATE TABLE translations (
    id SERIAL PRIMARY KEY,

    key VARCHAR(255),
    language VARCHAR(10),
    value TEXT
);

-- =====================================================
-- AI MODULE
-- =====================================================
CREATE TABLE ai_logs (
    id SERIAL PRIMARY KEY,

    user_id INT REFERENCES users(id),

    prompt TEXT,
    response TEXT,
    model VARCHAR(100),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- LABELS / BARCODE PRINTING
-- =====================================================
CREATE TABLE product_labels (
    id SERIAL PRIMARY KEY,

    product_id INT REFERENCES products(id),

    barcode_value VARCHAR(120),
    qr_code TEXT,

    template JSONB,
    printed BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- AUDIT LOGS
-- =====================================================
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,

    user_id INT REFERENCES users(id),

    action TEXT,
    table_name VARCHAR(100),
    record_id INT,

    old_data JSONB,
    new_data JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- SYSTEM SETTINGS (SMTP + APP CONFIG)
-- =====================================================
CREATE TABLE system_settings (
    id SERIAL PRIMARY KEY,

    smtp_host VARCHAR(255),
    smtp_port INT,
    smtp_user VARCHAR(255),
    smtp_password TEXT,
    smtp_encryption VARCHAR(20) CHECK (smtp_encryption IN ('none','ssl','tls')),

    default_sender_email VARCHAR(255),
    default_sender_name VARCHAR(150),

    app_name VARCHAR(150),
    timezone VARCHAR(50),

    enable_ai BOOLEAN DEFAULT TRUE,
    enable_notifications BOOLEAN DEFAULT TRUE,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- NOTIFICATIONS
-- =====================================================
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,

    user_id INT REFERENCES users(id),

    type VARCHAR(50),
    title VARCHAR(255),
    message TEXT,

    is_sent BOOLEAN DEFAULT FALSE,
    sent_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- INDEXES
-- =====================================================
CREATE INDEX idx_products_barcode ON products(barcode_primary);
CREATE INDEX idx_stock_product ON stock_movements(product_id);
CREATE INDEX idx_sales_date ON sales(created_at);
CREATE INDEX idx_ai_user ON ai_logs(user_id);
CREATE INDEX idx_payroll_employee ON payrolls(employee_id);
CREATE INDEX idx_users_email ON users(email);
