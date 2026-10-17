"""Generate the synthetic 200-table test schema in examples/synthetic/ (deterministic).

Covers: aliases, quoted names, every relationship operator, inline and `rel` relationships,
table-level relationships, composite keys, defaults, modifiers, doc comments, cross-file FKs.
"""

import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "examples" / "synthetic"
DOMAINS = {
    "sales": [
        "Customer",
        "Order",
        "OrderLine",
        "Invoice",
        "Quote",
        "Discount",
        "SalesRep",
        "Territory",
        "Channel",
        "Contract",
        "Refund",
        "Shipment",
        "Return",
        "Basket",
        "Coupon",
        "Lead",
        "Opportunity",
        "Account",
        "Region",
        "PriceList",
        "PriceListItem",
        "Subscription",
        "Plan",
        "PlanFeature",
        "Renewal",
        "Cart",
        "Payment",
        "PaymentMethod",
        "Promotion",
        "Commission",
        "Quota",
        "Forecast",
        "Deal",
        "DealStage",
        "Partner",
        "Reseller",
        "SalesNote",
        "Activity",
        "Campaign",
        "Segment",
    ],
    "finance": [
        "Ledger",
        "LedgerEntry",
        "Journal",
        "JournalLine",
        "Currency",
        "ExchangeRate",
        "TaxRate",
        "TaxCode",
        "CostCenter",
        "Budget",
        "BudgetLine",
        "FiscalYear",
        "FiscalPeriod",
        "Vendor",
        "Bill",
        "BillLine",
        "BankAccount",
        "BankTransaction",
        "Reconciliation",
        "Asset",
        "Depreciation",
        "Expense",
        "ExpenseClaim",
        "Approval",
        "AuditLog",
        "Allocation",
        "Accrual",
        "Provision",
        "Loan",
        "Repayment",
        "CreditNote",
        "DebitNote",
        "Settlement",
        "Chargeback",
        "Fee",
        "GLAccount",
        "GLGroup",
        "Entity",
        "Intercompany",
        "Consolidation",
    ],
    "inventory": [
        "Product",
        "ProductCategory",
        "Sku",
        "Warehouse",
        "Bin",
        "StockLevel",
        "StockMove",
        "Supplier",
        "PurchaseOrder",
        "PurchaseOrderLine",
        "Receipt",
        "ReceiptLine",
        "Batch",
        "SerialNumber",
        "Unit",
        "UnitConversion",
        "Bom",
        "BomLine",
        "WorkOrder",
        "Routing",
        "Operation",
        "Machine",
        "Shift",
        "QualityCheck",
        "Defect",
        "Carrier",
        "Route",
        "Stop",
        "Vehicle",
        "Driver",
        "Pallet",
        "Container",
        "Dock",
        "Appointment",
        "CycleCount",
        "Adjustment",
        "Reservation",
        "Kit",
        "KitItem",
        "Attribute",
    ],
    "hr": [
        "Employee",
        "Department",
        "Position",
        "JobGrade",
        "Salary",
        "Bonus",
        "Benefit",
        "Enrollment",
        "Leave",
        "LeaveType",
        "Timesheet",
        "TimesheetLine",
        "Project",
        "ProjectRole",
        "Skill",
        "EmployeeSkill",
        "Review",
        "Goal",
        "Training",
        "Course",
        "Certification",
        "Candidate",
        "Application",
        "Interview",
        "Offer",
        "Contractor",
        "Agency",
        "Location",
        "Holiday",
        "Payroll",
        "PayrollLine",
        "Deduction",
        "Pension",
        "Manager",
        "Team",
        "TeamMember",
        "Onboarding",
        "Exit",
        "Survey",
        "SurveyAnswer",
    ],
    "marketing": [
        "Audience",
        "AudienceMember",
        "Email",
        "EmailSend",
        "EmailOpen",
        "EmailClick",
        "LandingPage",
        "Visit",
        "PageView",
        "Form",
        "FormSubmission",
        "Ad",
        "AdGroup",
        "AdCampaign",
        "Keyword",
        "Impression",
        "Click",
        "Conversion",
        "Attribution",
        "UtmSource",
        "Content",
        "Asset2",
        "Tag",
        "ContentTag",
        "Webinar",
        "Registration",
        "Event",
        "EventAttendee",
        "Sponsor",
        "Influencer",
        "Post",
        "SocialAccount",
        "Mention",
        "Experiment",
        "Variant",
        "Assignment",
        "Score",
        "ScoreRule",
        "Persona",
        "Journey",
    ],
}
OPS = ["-", "-<", ">-", ">-<", "-0", "0-", "0-0", "-0<", ">0-"]
TYPES = ["int", "string", "varchar(200)", "decimal(10,2)", "datetime", "bool", "money", "uuid", "text", "date"]


def main() -> None:
    rnd = random.Random(42)
    OUT.mkdir(parents=True, exist_ok=True)
    defined: list[tuple[str, str, str]] = []  # (reference name, plain name, pk column)
    op_i = 0
    for domain, names in DOMAINS.items():
        lines = [f"# Synthetic {domain} schema (generated by scripts/gen_schema.py)", ""]
        for i, name in enumerate(names):
            alias = f"{name[:3].lower()}{i}" if i % 7 == 0 else None
            display = f'"{domain}.{name}"' if i % 13 == 5 else name
            if i % 5 == 0:
                lines.append(f"# {name} documentation")
            lines.append(display + (f" as {alias}" if alias else ""))
            ref_table = None
            if i % 11 == 3 and defined:
                # `rel` lines are split on whitespace only, so they can't target quoted names.
                ref_table = rnd.choice([d for d in defined if not d[0].startswith('"')])[0]
                lines.append(f"rel >- {ref_table}")
            lines.append("-" * rnd.choice([1, 3, 4, 10]))
            lines.append(f"{name}Id PK int IDENTITY")
            for k in range(rnd.randint(0, 2)):
                if not defined:
                    break
                target = rnd.choice(defined)
                op = OPS[op_i % len(OPS)]
                op_i += 1
                ref, plain, pk = target
                lines.append(f"{plain}Ref{k} int FK {op} {ref}.{pk}")
            for k in range(rnd.randint(1, 9)):
                t = rnd.choice(TYPES)
                mods = rnd.choice(["", " NULL", " UNIQUE", " INDEX", f" default={rnd.randint(0, 9)}", ""])
                lines.append(f"Field{k}{name} {t}{mods}")
            if i % 17 == 2:
                lines.append(f'"Display Name" string="Unnamed {name}"')
            lines.append("")
            ref_name = display if display.startswith('"') else name
            defined.append((alias or ref_name, name, f"{name}Id"))
        (OUT / f"{domain}.txt").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
