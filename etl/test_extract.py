from pprint import pprint

from openpyxl import load_workbook

from etl.extract.m_quotation import extract_m_quotation
from etl.extract.o_quotation import extract_o_quotation
from etl.extract.kit_detail import extract_kit_detail


# =========================
# Test settings
# =========================

M_FILE_PATH = "data/raw/KP-M-Q-26-000 FROM START HERE.xlsx"
M_SHEET_NAME = "quote25-090(AMENDED)"

O_FILE_PATH = "data/raw/KP-O-Q-26-000.xlsx"
O_SHEET_NAME = "022(ONE TRIUMPH)"

KIT_FILE_PATH = "data/raw/KP-O-Q-26-000.xlsx"
KIT_SHEET_NAME = "022 KIT"


# =========================
# M quotation test
# =========================

m_workbook = load_workbook(
    M_FILE_PATH,
    data_only=True
)

m_sheet = m_workbook[M_SHEET_NAME]

m_data = extract_m_quotation(m_sheet)

print("\n=== M QUOTATION ===")
pprint(m_data)


# =========================
# O quotation test
# =========================

o_workbook = load_workbook(
    O_FILE_PATH,
    data_only=True
)

o_sheet = o_workbook[O_SHEET_NAME]

o_data = extract_o_quotation(o_sheet)

print("\n=== O QUOTATION ===")
pprint(o_data)


# =========================
# KIT detail test
# =========================

kit_workbook = load_workbook(
    KIT_FILE_PATH,
    data_only=True
)

kit_sheet = kit_workbook[KIT_SHEET_NAME]

kit_data = extract_kit_detail(kit_sheet)

print("\n=== KIT DETAIL ===")
pprint(kit_data)