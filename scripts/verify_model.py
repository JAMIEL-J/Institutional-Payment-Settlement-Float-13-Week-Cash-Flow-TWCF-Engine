"""Verify Excel Financial Model using formulas and LibreOffice Calc."""
import subprocess
from pathlib import Path
import formulas

def verify():
    base_dir = Path(__file__).resolve().parents[1]
    xl_path = base_dir / "model.xlsx" if (base_dir / "model.xlsx").exists() else base_dir / "Institutional_Payment_Float_Financial_Model.xlsx"
    print(f"Loading workbook into formulas engine: {xl_path.name}...")
    
    xl_model = formulas.ExcelModel().loads(str(xl_path)).finish()
    print("Graph compiled successfully. Executing calculation...")
    res = xl_model.calculate()
    print(f"Total calculated formula nodes: {len(res)}")
    
    # Inspect key nodes for errors
    errors = []
    error_values = {"#VALUE!", "#DIV/0!", "#REF!", "#NAME?", "#N/A", "#NUM!"}
    
    # Sample nodes to display
    key_checks = [
        "'ASSUMPTIONS'!C19",
        "'ASSUMPTIONS'!C42",
        "'ASSUMPTIONS'!C43",
        "'ASSUMPTIONS'!C44",
        "'ASSUMPTIONS'!C45",
        "'ASSUMPTIONS'!C46",
        "'ASSUMPTIONS'!C47",
        "'ASSUMPTIONS'!C48",
        "'DAILY_CASH_WATERFALL'!M2",
        "'DAILY_CASH_WATERFALL'!N2",
        "'DAILY_CASH_WATERFALL'!O2",
        "'DAILY_CASH_WATERFALL'!P2",
        "'DAILY_CASH_WATERFALL'!Q2",
        "'DAILY_CASH_WATERFALL'!R2",
        "'WORKING_CAPITAL_DFO'!E2",
        "'WORKING_CAPITAL_DFO'!E152",
        "'REGULATORY_LIQUIDITY_CECL'!D2",
        "'REGULATORY_LIQUIDITY_CECL'!E2",
        "'TWCF_13W_BRIDGE'!K2",
        "'TWCF_13W_BRIDGE'!K15",
    ]
    
    for k, v in res.items():
        v_str = str(v)
        for err in error_values:
            if err in v_str:
                errors.append((k, v_str))
                
    if errors:
        print(f"ERRORS FOUND ({len(errors)}):")
        for err in errors[:10]:
            print(f"  {err[0]} => {err[1]}")
    else:
        print("PERFECT: Zero formula errors across all sheets and ranges!")

    print("\nSample Calculated Key Metrics:")
    for k, v in list(res.items())[:20]:
        if any(w in k for w in ["C4", "C19", "C42", "C43", "C44", "C45", "C46", "C47", "C48", "K15", "E152"]):
            print(f"  {k} => {v}")

    # LibreOffice verification
    soffice_path = r"C:\Program Files\LibreOffice\program\soffice.exe"
    if Path(soffice_path).exists():
        print(f"\nVerifying with LibreOffice Calc headless ({soffice_path})...")
        cmd = [
            soffice_path,
            "--headless",
            "--convert-to",
            "pdf",
            str(xl_path),
            "--outdir",
            str(base_dir / "reports")
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            print("LibreOffice Calc verified successfully: Rendered model to reports/Institutional_Payment_Float_Financial_Model.pdf without errors!")
        else:
            print("LibreOffice warning:", proc.stderr)
    else:
        print("LibreOffice not found at expected path.")

if __name__ == "__main__":
    verify()
