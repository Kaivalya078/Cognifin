"""
Names people actually type, mapped to the NSE symbols the corpus is keyed by.

Bare group names ("Tata", "HDFC", "Bajaj", "Adani") are deliberately absent:
they name several listed companies. Longer names win over shorter ones
("SBI Life" over "SBI", "Tech Mahindra" over "Mahindra") — see
query_understanding.detect_companies.
"""

COMPANY_ALIASES = {
    "ADANIENT": ["Adani Enterprises"],
    "ADANIPORTS": ["Adani Ports", "Adani Ports and SEZ", "APSEZ"],
    "APOLLOHOSP": ["Apollo Hospitals", "Apollo"],
    "ASIANPAINT": ["Asian Paints"],
    "AXISBANK": ["Axis Bank"],
    "BAJAJ-AUTO": ["Bajaj Auto"],
    "BAJAJFINSV": ["Bajaj Finserv"],
    "BAJFINANCE": ["Bajaj Finance"],
    "BEL": ["Bharat Electronics"],
    "BHARTIARTL": ["Bharti Airtel", "Airtel", "Bharti"],
    "COALINDIA": ["Coal India"],
    "DRREDDY": ["Dr. Reddy's", "Dr Reddy's", "Dr. Reddys", "Dr Reddys", "Dr. Reddy", "Dr Reddy"],
    "EICHERMOT": ["Eicher Motors", "Eicher", "Royal Enfield"],
    "HCLTECH": ["HCL Technologies", "HCLTech", "HCL Tech", "HCL"],
    "HDFCBANK": ["HDFC Bank"],
    "HDFCLIFE": ["HDFC Life"],
    "HINDUNILVR": ["Hindustan Unilever", "HUL"],
    "ICICIBANK": ["ICICI Bank", "ICICI"],
    "INDIGO": ["InterGlobe Aviation", "InterGlobe"],
    "INFY": ["Infosys"],
    "JIOFIN": ["Jio Financial Services", "Jio Financial"],
    "JSWSTEEL": ["JSW Steel"],
    "KOTAKBANK": ["Kotak Mahindra Bank", "Kotak Bank", "Kotak"],
    "LT": ["Larsen & Toubro", "Larsen and Toubro", "L&T"],
    "M&M": ["Mahindra & Mahindra", "Mahindra and Mahindra", "Mahindra"],
    "MARUTI": ["Maruti Suzuki", "Maruti"],
    "MAXHEALTH": ["Max Healthcare"],
    "NESTLEIND": ["Nestle India", "Nestlé India", "Nestle", "Nestlé"],
    "ONGC": ["Oil and Natural Gas Corporation"],
    "POWERGRID": ["Power Grid Corporation", "Power Grid"],
    "RELIANCE": ["Reliance Industries", "RIL"],
    "SBILIFE": ["SBI Life"],
    "SBIN": ["State Bank of India", "SBI"],
    "SHRIRAMFIN": ["Shriram Finance"],
    "TATACONSUM": ["Tata Consumer Products", "Tata Consumer"],
    "TATASTEEL": ["Tata Steel"],
    "TCS": ["Tata Consultancy Services"],
    "TECHM": ["Tech Mahindra"],
    "TITAN": ["Titan Company"],
    "TMPV": ["Tata Motors"],
    "ULTRACEMCO": ["UltraTech Cement", "UltraTech"],
}
