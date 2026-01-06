# 🧮 Data Mart & Credit Rating System

**Repository:** [https://github.com/VIVEK-MARRI/data-mart-credit-rating-reporting](https://github.com/VIVEK-MARRI/data-mart-credit-rating-reporting)  
**Author:** Vivek Marri  
**Institution:** JNTUH University College of Engineering, Manthani  
**Date:** 09-Nov-2025  

---

## 📘 Project Overview  
This project delivers a complete enterprise-style solution for **credit rating analytics** by designing and implementing a **Data Mart architecture** that consolidates, integrates, and visualizes credit rating data from multiple sources.  

### 🔑 Key Highlights:
- PostgreSQL-based **data mart** using **Star Schema** for efficient analytics.  
- Automated **ETL pipeline** (Python + Pandas + SQLAlchemy) for data ingestion and transformation.  
- **SCD Type-2** implementation for maintaining historical rating changes.  
- Interactive **Tableau dashboards** for rating trends, vendor insights, and country comparisons.  
- Modular, scalable, and ready for cloud or predictive analytics extension.  

---

## 🗂️ Repository Structure

```bash
data-mart-credit-rating-reporting/
│
├── data/
│   └── processed/                     # Cleaned CSV data files
│       ├── transactions_cleaned.csv
│       ├── outlier_precision_by_security_date.csv
│       ├── rating_frequency_per_vendor_year.csv
│       └── ratings_type2_sample.csv
│
├── scripts/
│   ├── create_schema.sql              # PostgreSQL schema + table definitions
│   └── load_datamart_postgres.py      # Python ETL script
│
├── .env.example                       # Example environment file
├── requirements.txt                   # Python dependencies
├── README.md                          # Project documentation
└── LICENSE (optional)
```
---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- PostgreSQL 15 or higher
- pgAdmin or SQL client (optional)
- Tableau Desktop or Tableau Public (for visualization)
- Git & GitHub for version control

### Installation & Setup

1. **Clone the repository:**
    ```
    git clone https://github.com/VIVEK-MARRI/data-mart-credit-rating-reporting.git
    cd data-mart-credit-rating-reporting
    ```

2. **Create and activate a virtual environment:**
    ```
    python -m venv venv
    # Windows:
    venv\Scripts\activate
    # macOS/Linux:
    source venv/bin/activate
    ```

3. **Install Python dependencies:**
    ```
    pip install -r requirements.txt
    ```

4. **Create a `.env` file at the project root with your database credentials:**
    ```
    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=credit_rating_dm
    DB_USER=postgres
    DB_PASSWORD=your_password
    DB_SCHEMA=credit_dm
    ```

5. **Initialize the database schema:**
    - Open pgAdmin or use a SQL client.
    - Run the script:
        ```
        \i scripts/create_schema.sql
        ```

6. **Load data into the data mart by running the ETL pipeline:**
    ```
    python scripts/load_datamart_postgres.py
    ```

7. **Verify that tables have loaded data:**
    ```
    SELECT COUNT(*) FROM credit_dm.dim_security;
    SELECT COUNT(*) FROM credit_dm.fact_ratings_scd;
    ```

8. **Visualize the data in Tableau:**
    - Open Tableau and connect to PostgreSQL:
        - Server: localhost
        - Database: credit_rating_dm
        - Username/Password: as configured
    - Select schema `credit_dm`, import relevant tables.
    - Explore dashboards summarizing credit trends, vendor performance, outlier severity, etc.

---

## 📊 Dashboards & Insights

- **Dashboard 1: Credit Rating KPI Dashboard (2021–2025)**
    - High-level KPIs including upgrades, downgrades, net rating change and precision score by year and vendor.
- **Dashboard 2: Vendor & Country Performance Insights**
    - Comparative analytics of rating distribution across vendors and countries, outlier severity, and top outlier securities.

These dashboards enable **data-driven decision-making** by providing clear visual insights into credit rating behavior, vendor effectiveness and regional patterns.

---

## ✅ Key Achievements

- Centralized data from disparate sources into a unified data mart.
- Built a robust ETL pipeline automating processing, cleansing, mapping and loading of credit rating data.
- Designed a star schema with dimensions and fact tables to optimize analytical workloads and reporting.
- Implemented SCD Type-2 to maintain historic rating versions and enable temporal analysis.
- Developed Tableau dashboards to visualize insights and support credit risk assessment workflows.
- Established a foundation for future improvement including cloud migration, real-time ingestion and predictive modelling.

---

## 🔮 Future Enhancements Scope

- Real-time data streaming (Kafka, NiFi) for continuous updates.
- Cloud deployment on AWS, Azure or GCP for enterprise scaling.
- Machine learning for rating prediction and anomaly detection.
- Role-based access, encryption, and advanced security controls.
- Web interface for non-technical users to trigger ETL runs and interact with dashboards.
- Extended data quality frameworks, monitoring and logging.

---

## 📚 References

- PostgreSQL Documentation: [https://www.postgresql.org/docs/](https://www.postgresql.org/docs/)
- Python Official Documentation: [https://docs.python.org/3/](https://docs.python.org/3/)
- pandas Documentation: [https://pandas.pydata.org/docs/](https://pandas.pydata.org/docs/)
- SQLAlchemy Documentation: [https://docs.sqlalchemy.org/](https://docs.sqlalchemy.org/)
- NumPy Documentation: [https://numpy.org/doc/](https://numpy.org/doc/)
- Tableau Help Guide: [https://help.tableau.com/](https://help.tableau.com/)
- dotenv: [https://pypi.org/project/python-dotenv/](https://pypi.org/project/python-dotenv/)

---

## 🤝 Acknowledgements

I would like to express my sincere gratitude to Tata Consultancy Services (TCS) for providing this industry-aligned project opportunity, and to JNTUH University College of Engineering, Manthani for their academic support and encouragement. I also thank the open-source communities behind Python, PostgreSQL, pandas, SQLAlchemy and Tableau whose tools and documentation made this project possible.

---

## 📝 License

This repository is for academic/educational purposes.  
Please reach out for licensing or enterprise usage.
