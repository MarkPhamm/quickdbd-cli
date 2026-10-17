"""Parser corpus: behaviour matched against QuickDBD's own parser (app bundle v2.4.427.0)."""

import textwrap

import pytest

from quickdbd_cli.parser import compile_sources, compile_text, encode, line_data, tokenize_field_line


def c(text):
    return compile_text(textwrap.dedent(text).strip("\n"), "s.txt")


def errs(text):
    return [(d.line, d.message) for d in c(text).errors]


def warns(text):
    return [(d.line, d.message) for d in c(text).warnings]


SAMPLE = """
Customer
-
CustomerID PK int
Name string INDEX
Address1 string
Address2 NULL string

Order
-
OrderID PK int
CustomerID int FK >- Customer.CustomerID
TotalAmount money
OrderStatusID int FK >- os.OrderStatusID

OrderLine as ol
----
OrderLineID PK int
OrderID int FK >- Order.OrderID
ProductID int FK >- p.ProductID
Quantity int

# Table documentation comment 1
Product as p # Table documentation comment 2
------------
ProductID PK int
# Field documentation comment 1
Name varchar(200) UNIQUE # Field documentation comment 3
Price money

OrderStatus as os
----
OrderStatusID PK int
Name UNIQUE string
"""


def test_sample_parses_clean():
    s = c(SAMPLE)
    assert s.diagnostics == []
    assert list(s.tables) == ["Customer", "Order", "OrderLine", "Product", "OrderStatus"]
    assert s.tables["OrderLine"].aliases == ["ol"]
    assert len(s.relationships) == 4


def test_columns_and_flags():
    s = c(SAMPLE)
    cust = s.tables["Customer"].columns
    assert [k for k in cust] == ["CustomerID", "Name", "Address1", "Address2"]
    assert cust["CustomerID"].pk and cust["CustomerID"].type == "int"
    assert cust["Name"].index
    assert cust["Address2"].nullable and cust["Address2"].type == "string"
    assert s.tables["Product"].columns["Name"].type == "varchar(200)"
    assert s.tables["Product"].columns["Name"].unique


def test_relationship_resolution_with_alias():
    s = c(SAMPLE)
    rel = s.relationships[1]
    assert (rel.a.table, rel.a.column, rel.a.card) == ("Order", "OrderStatusID", "many")
    assert (rel.b.table, rel.b.column, rel.b.card) == ("OrderStatus", "OrderStatusID", "one")


def test_fk_flag_set_on_non_pk_member():
    s = c(SAMPLE)
    assert s.tables["Order"].columns["CustomerID"].fk
    assert not s.tables["Customer"].columns["CustomerID"].fk


def test_doc_comments():
    s = c(SAMPLE)
    assert s.tables["Product"].comments == ["Table documentation comment 1", "Table documentation comment 2"]
    assert s.tables["Product"].columns["Name"].comments == ["Field documentation comment 1", "Field documentation comment 3"]


@pytest.mark.parametrize(
    "op,cards",
    [
        ("-", ("one", "one")),
        ("-<", ("one", "many")),
        (">-", ("many", "one")),
        (">-<", ("many", "many")),
        ("-0", ("one", "zeroOne")),
        ("0-", ("zeroOne", "one")),
        ("0-0", ("zeroOne", "zeroOne")),
        ("-0<", ("one", "zeroMany")),
        (">0-", ("zeroMany", "one")),
    ],
)
def test_all_operators(op, cards):
    s = c(f"""
        A
        -
        Id PK int
        BId int FK {op} B.Id

        B
        -
        Id PK int
        """)
    assert s.errors == []
    r = s.relationships[0]
    assert (r.a.card, r.b.card) == cards


def test_forward_reference_ok():
    assert errs("""
        A
        -
        BId int FK >- B.Id

        B
        -
        Id PK int
        """) == []


def test_separator_any_length():
    for sep in ["-", "--", "-----------"]:
        s = c(f"T\n{sep}\nId int")
        assert s.errors == [] and "Id" in s.tables["T"].columns


def test_comment_only_lines_do_not_break_table():
    s = c("T\n-\nA int\n# note\nB int")
    assert list(s.tables["T"].columns) == ["A", "B"]


def test_whitespace_only_line_breaks_table():
    s = c("T\n-\nA int\n   \nB int")
    # "B int" becomes its own table header that is invalid (contains a space)
    assert (5, "Invalid table name (use double quotes)") in [(d.line, d.message) for d in s.errors]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("-\nA int", [(1, "Table name not defined")]),
        ("T\n-\nA int\n\nT\n-\nB int", [(5, "Table 'T' already defined")]),
        ("T\n-\nA int\nA string", [(4, "Table field 'A' already defined")]),
        ("T\n-\nA int foo", [(3, "Unrecognized keyword 'foo'")]),
        ("T\n-\nA int FK >-", [(3, "Relationship key cannot be empty")]),
        ("T\nfoo\n-\nA int", [(2, "Unrecognized table metadata 'foo'")]),
        ("T\nrel - U a b\n-\nA int", [(2, "Unknown relationship param 'a'")]),
        ("Bad Name\n-\nA int", [(1, "Invalid table name (use double quotes)")]),
        ("dbo.Customer\n-\nA int", [(1, "Invalid table name (use double quotes)")]),
        ("T\n-\nA int FK >- U.Id", [(3, "Invalid relationship, the table 'U' does not exist")]),
        ("T\n-\nA int FK >- T.Nope", [(3, "Invalid relationship, the field 'T.Nope' does not exist")]),
        ("T\n-\nA int FK >- T.A.B", [(3, "Multi-nested relationships are not allowed")]),
        ("T\n-\nA PK UNIQUE int", [(3, "The field cannot be a primary key and an unique key, since a primary key is unique")]),
        ("T\n-\nA PK INDEX int", [(3, "The field cannot be a primary key and an index, since a primary key is an index")]),
        ("T\n-\nA UNIQUE INDEX int", [(3, "The field cannot be an unique key and an index, since an unique key is an index")]),
        ("[foo]", [(1, "Invalid section name '[foo]' (allowed: tables, settings, layout)")]),
        ("[settings]\nZoom 100\n[settings]", [(3, "Section '[settings]' is already defined")]),
        ("[layout]\n[settings]", [(2, "Section '[settings]' is out of order. It must be defined before: '[layout]'")]),
        ("[settings]\nZoom 500", [(2, "Invalid 'Zoom' value (allowed: number between 10 and 200)")]),
        ("[settings]\nCaseSensitive maybe", [(2, "Invalid 'CaseSensitive' value (allowed: 'on', 'off')")]),
        ("[settings]\nZoom", [(2, "Setting value missing")]),
        ("[settings]\nZoom 100\nzoom 90", [(3, "Setting 'zoom' already defined")]),
        ("[settings]\nPosition 10", [(2, "Position setting requires 2 values (x, y)")]),
        ("[settings]\nPosition a 10", [(2, "Invalid X coordinate 'a', number expected")]),
        ("T\n-\nA int\n[layout]\nT 1", [(5, "Layout definition requires 3 values (tableName, x, y)")]),
        ("T\n-\nA int\n[layout]\nT x 1", [(5, "Invalid X coordinate 'x', number expected")]),
        ("T\n-\nA int\n[layout]\nT 1 y", [(5, "Invalid Y coordinate 'y', number expected")]),
        ("T\n-\nA int\n[layout]\nT 1 2\nT 3 4", [(6, "Layout for 'T' already defined")]),
    ],
)
def test_error_messages(text, expected):
    assert [(d.line, d.message) for d in compile_text(text, "s.txt").errors] == expected


def test_invalid_relationship_description():
    msg = "Invalid relationship description (allowed: -, -<, >-, >-<, -0, 0-, 0-0, -0<, >0-)"
    s = c("""
        T
        rel <> U
        -
        A int

        U
        -
        B int
        """)
    assert [(d.line, d.message) for d in s.errors] == [(2, msg)]


def test_duplicate_relationship_either_direction():
    e = errs("""
        A
        -
        Id PK int
        BId int FK >- B.Id

        B
        -
        Id PK int FK -< A.BId
        """)
    assert e == [(8, "Relationship already defined at line 4")]


def test_table_level_relationship_and_virtual_field():
    s = c("""
        A
        rel >- B
        -
        Id int

        B
        -
        ..
        Id int
        """)
    assert s.errors == []
    r = s.relationships[0]
    assert (r.a.table, r.a.column, r.b.table, r.b.column) == ("A", "qdbdvirtualfield", "B", "qdbdvirtualfield")
    assert s.tables["A"].columns["qdbdvirtualfield"].virtual


def test_rel_metadata_default_operator():
    s = c("A\nrel B\n-\nId int\n\nB\n-\nId int")
    assert (s.relationships[0].a.card, s.relationships[0].b.card) == ("one", "one")


def test_quoted_names_and_targets():
    s = c("""
        "dbo.Customer" as c
        -
        "Customer Id" PK int

        Order
        -
        CustId int FK >- "dbo.Customer"."Customer Id"
        Other int FK >- c."Customer Id"
        """)
    assert s.errors == []
    t = s.tables[encode("dbo.Customer")]
    assert t.name == "dbo.Customer"
    assert t.columns[encode("Customer Id")].name == "Customer Id"
    assert s.relationships[0].b.table == t.id


def test_type_with_default_and_quoted_default():
    s = c("""
        T
        -
        A int=27
        B string="Some default address"
        C datetime default=GETUTCDATE()
        """)
    cols = s.tables["T"].columns
    assert (cols["A"].type, cols["A"].default) == ("int", "27")
    assert (cols["B"].type, cols["B"].default) == ("string", "Some default address")
    # Deviation: QuickDBD lowercases default= values; we keep the original case.
    assert cols["C"].default == "GETUTCDATE()"


def test_modifiers_any_order_case_insensitive():
    s = c("T\n-\nId int pk identity\nX null Unique varchar(10)\nY AUTOINCREMENT nullable int")
    cols = s.tables["T"].columns
    assert cols["Id"].pk and cols["Id"].identity and cols["Id"].type == "int"
    assert cols["X"].nullable and cols["X"].unique and cols["X"].type == "varchar(10)"
    assert cols["Y"].identity and cols["Y"].nullable


def test_composite_pk():
    s = c("T\n-\nA PK int\nB PK int")
    assert s.tables["T"].columns["A"].pk and s.tables["T"].columns["B"].pk


def test_fk_without_relationship_then_type():
    s = c("T\n-\nA FK int")
    col = s.tables["T"].columns["A"]
    assert col.fk and col.type == "int" and s.relationships == []


def test_case_insensitive_lookup_default():
    assert errs("A\n-\nId PK int\n\nB\n-\nAId int FK >- a.id") == []


def test_case_sensitive_setting():
    e = errs("A\n-\nId PK int\n\nB\n-\nAId int FK >- a.id\n\n[settings]\nCaseSensitive on")
    assert e == [(7, "Invalid relationship, the table 'a' does not exist")]


def test_multiple_aliases():
    s = c("Order as o, ord\n-\nId PK int\n\nX\n-\nA int FK >- o.Id\nB int FK >- ord.Id")
    assert s.errors == []
    assert s.tables["Order"].aliases == ["o", "ord"]


def test_hash_inside_quotes_is_not_comment():
    assert line_data('A string="x # y" # real') == ('A string="x # y"', "real")


def test_tokenize_quoted_encodes():
    toks = tokenize_field_line('A int FK >- "My Table".Id')
    assert toks[-1].value == "My Table.Id"
    assert toks[-1].encoded == "My32Table.Id"


def test_general_comments_before_first_table():
    s = c("# about this schema\n\nT\n-\nA int")
    assert s.general_comments == ["about this schema"]


def test_settings_and_layout():
    s = c("T\n-\nA int\n\n[settings]\nZoom 80\nPosition 10 20\n\n[layout]\nT 100 200")
    assert s.errors == []
    assert s.zoom == 80 and s.position == (10, 20)
    assert s.layout == {"T": (100.0, 200.0)}


def test_default_field_type():
    s = c("T\n-\nA\nB string\n\n[settings]\nDefaultFieldType int")
    assert s.tables["T"].columns["A"].type == "int"
    assert s.tables["T"].columns["B"].type == "string"


def test_crlf_line_endings():
    s = compile_text("T\r\n-\r\nA int\r\n", "s.txt")
    assert s.errors == [] and "A" in s.tables["T"].columns


# ---------------------------------------------------------------- forgiving deviations (warnings)


def test_tabs_warn_not_error():
    s = c("T\n-\nA\tint")
    assert s.errors == []
    assert s.tables["T"].columns["A"].type == "int"
    assert len(s.warnings) == 1 and "tab" in s.warnings[0].message


def test_spaces_inside_type_parens():
    s = c("T\n-\nA decimal(10, 2) NULL")
    assert s.errors == []
    assert s.tables["T"].columns["A"].type == "decimal(10,2)"
    assert s.tables["T"].columns["A"].nullable
    assert len(s.warnings) == 1


def test_explicit_not_null():
    s = c("T\n-\nA int NOT NULL")
    assert s.errors == []
    assert not s.tables["T"].columns["A"].nullable
    assert len(s.warnings) == 1


def test_indented_table_header():
    s = c("  T\n  ---\nA int")
    assert s.errors == [] and "T" in s.tables
    assert len(s.warnings) == 2


def test_layout_unknown_table_is_warning():
    s = c("T\n-\nA int\n\n[layout]\nNope 1 2")
    assert s.errors == [] and len(s.warnings) == 1


# ---------------------------------------------------------------- multi-file


def test_multi_file_cross_reference():
    s = compile_sources([("a.txt", "A\n-\nId PK int"), ("b.txt", "B\n-\nAId int FK >- A.Id")])
    assert s.errors == []
    assert s.relationships[0].b.table == "A"


def test_multi_file_duplicate_table():
    s = compile_sources([("a.txt", "A\n-\nId PK int"), ("b.txt", "A\n-\nId PK int")])
    assert [d.format() for d in s.errors] == ["b.txt:1: error: Table 'A' already defined (first defined at a.txt:1)"]


def test_multi_file_alias_across_files():
    s = compile_sources([("a.txt", "Alpha as a\n-\nId PK int"), ("b.txt", "B\n-\nAId int FK >- a.Id")])
    assert s.errors == []


def test_diagnostic_format():
    s = compile_text("T\n-\nA int foo", "x/schema.txt")
    assert s.errors[0].format() == "x/schema.txt:3: error: Unrecognized keyword 'foo'"
