# SYNTHETIC DATA · for training only · no OSFI data
"""
build_rdl.py - writes paginated/rpt_fda_institution_return.rdl (RDL 2016) against sm_fda_supervisory.

Placeholders replaced by scripts/01-Deploy-FdaEnvironment.ps1 before the Power BI Imports API upload:
  __TENANT_ID__   Entra tenant id
  __DATASET_ID__  sm_fda_supervisory semantic model id
Generated output is committed. Run:  python paginated/build_rdl.py
"""
from __future__ import annotations

import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
BANNER = "SYNTHETIC DATA · for training only · no OSFI data"
FONT = "Segoe UI"
TEAL, DARK, RED = "#1FB58F", "#1F1F1F", "#C00000"

CONNECT = ('Data Source=pbiazure://api.powerbi.com/;Identity Provider="https://login.microsoftonline.com/common, '
           'https://analysis.windows.net/powerbi/api, __TENANT_ID__";Initial Catalog=sobe_wowvirtualserver-__DATASET_ID__;'
           'Integrated Security=ClaimsToken')

DAX_INSTITUTIONS = """// SYNTHETIC DATA - institution list for the Institution parameter
EVALUATE
SELECTCOLUMNS(
    dim_institution,
    "code", dim_institution[institution_code],
    "label", dim_institution[institution_name] & " (" & dim_institution[institution_code] & ")"
)
ORDER BY [label]"""

DAX_RETURN = """// SYNTHETIC DATA - last 8 quarters of key ratios for the selected institutions
DEFINE
    MEASURE fact_insurance_capital[Insurer Watch Threshold (report)] =
        VAR _type = SELECTEDVALUE(dim_institution[institution_type])
        RETURN
            CALCULATE(
                MAX(supervisory_watch_thresholds[watch_threshold]),
                supervisory_watch_thresholds[metric] IN {"LICAT total", "MCT"},
                supervisory_watch_thresholds[institution_type] = _type
            )
    VAR _currentIndex = CALCULATE(MAX(dim_quarter[quarter_index]), dim_quarter[is_current] = TRUE())
EVALUATE
SUMMARIZECOLUMNS(
    dim_institution[institution_code],
    dim_institution[institution_name],
    dim_institution[institution_type],
    dim_institution[supervisory_lead],
    dim_quarter[quarter_key],
    dim_quarter[quarter_label],
    FILTER(VALUES(dim_institution[institution_code]), PATHCONTAINS(@InstitutionList, dim_institution[institution_code])),
    FILTER(VALUES(dim_quarter[quarter_index]), dim_quarter[quarter_index] > _currentIndex - 8),
    "Reporting", [Institutions Reporting],
    "CET1Ratio", [CET1 Ratio],
    "Tier1Ratio", [Tier 1 Ratio],
    "TotalCapitalRatio", [Total Capital Ratio],
    "LeverageRatio", [Leverage Ratio],
    "LCR", [LCR],
    "NSFR", [NSFR],
    "InsuranceCapitalRatio", [Insurance Capital Ratio],
    "CET1WatchThreshold", [CET1 Watch Threshold],
    "InsurerWatchThreshold", [Insurer Watch Threshold (report)]
)
ORDER BY dim_institution[institution_code], dim_quarter[quarter_key]"""

FIELDS_RETURN = [
    ("institution_code", "dim_institution[institution_code]", "System.String"),
    ("institution_name", "dim_institution[institution_name]", "System.String"),
    ("institution_type", "dim_institution[institution_type]", "System.String"),
    ("supervisory_lead", "dim_institution[supervisory_lead]", "System.String"),
    ("quarter_key", "dim_quarter[quarter_key]", "System.Int64"),
    ("quarter_label", "dim_quarter[quarter_label]", "System.String"),
    ("Reporting", "[Reporting]", "System.Int64"),
    ("CET1Ratio", "[CET1Ratio]", "System.Double"),
    ("Tier1Ratio", "[Tier1Ratio]", "System.Double"),
    ("TotalCapitalRatio", "[TotalCapitalRatio]", "System.Double"),
    ("LeverageRatio", "[LeverageRatio]", "System.Double"),
    ("LCR", "[LCR]", "System.Double"),
    ("NSFR", "[NSFR]", "System.Double"),
    ("InsuranceCapitalRatio", "[InsuranceCapitalRatio]", "System.Double"),
    ("CET1WatchThreshold", "[CET1WatchThreshold]", "System.Double"),
    ("InsurerWatchThreshold", "[InsurerWatchThreshold]", "System.Double"),
]
FIELDS_INST = [("code", "[code]", "System.String"), ("label", "[label]", "System.String")]

# (header, width in, value expression, format, color expression or None)
COLUMNS = [
    ("Quarter", 0.95, '=Fields!quarter_label.Value & IIF(IsNothing(Fields!Reporting.Value), " (not filed)", "")', None, None),
    ("CET1 ratio", 0.8, "=Fields!CET1Ratio.Value", "0.00%",
     f'=IIF(Not IsNothing(Fields!CET1Ratio.Value) And Not IsNothing(Fields!CET1WatchThreshold.Value) And Fields!CET1Ratio.Value < Fields!CET1WatchThreshold.Value, "{RED}", "{DARK}")'),
    ("Tier 1 ratio", 0.75, "=Fields!Tier1Ratio.Value", "0.00%", None),
    ("Total capital", 0.8, "=Fields!TotalCapitalRatio.Value", "0.00%", None),
    ("Leverage", 0.75, "=Fields!LeverageRatio.Value", "0.00%", None),
    ("LCR", 0.75, "=Fields!LCR.Value", "0.0%", None),
    ("NSFR", 0.75, "=Fields!NSFR.Value", "0.0%", None),
    ("LICAT / MCT", 0.85, "=Fields!InsuranceCapitalRatio.Value", "0.0%",
     f'=IIF(Not IsNothing(Fields!InsuranceCapitalRatio.Value) And Not IsNothing(Fields!InsurerWatchThreshold.Value) And Fields!InsuranceCapitalRatio.Value < Fields!InsurerWatchThreshold.Value, "{RED}", "{DARK}")'),
    ("Watch threshold", 0.9, '=IIF(Fields!institution_type.Value = "Life insurer" Or Fields!institution_type.Value = "P&C insurer", Fields!InsurerWatchThreshold.Value, Fields!CET1WatchThreshold.Value)', "0.0%", None),
]
BODY_WIDTH = sum(c[1] for c in COLUMNS)   # 7.5in = Letter 8.5in - 2 x 0.5in margins


def textbox(name, value, *, fmt=None, color=DARK, bold=False, size="9pt", align=None, fill=None,
            top=None, left=None, height=None, width=None, border=True, can_grow=True):
    style_run = [f"<FontFamily>{FONT}</FontFamily>", f"<FontSize>{size}</FontSize>"]
    if bold:
        style_run.append("<FontWeight>Bold</FontWeight>")
    if fmt:
        style_run.append(f"<Format>{escape(fmt)}</Format>")
    style_run.append(f"<Color>{escape(color)}</Color>")
    para_style = f"<Style><TextAlign>{align}</TextAlign></Style>" if align else "<Style />"
    pos = ""
    if top is not None:
        pos = f"<Top>{top}in</Top><Left>{left}in</Left><Height>{height}in</Height><Width>{width}in</Width>"
    box_style = ["<Border><Color>#D9D9D9</Color><Style>Solid</Style></Border>" if border else "<Border><Style>None</Style></Border>"]
    if fill:
        box_style.append(f"<BackgroundColor>{fill}</BackgroundColor>")
    box_style.append("<VerticalAlign>Middle</VerticalAlign>")
    box_style += ["<PaddingLeft>3pt</PaddingLeft>", "<PaddingRight>3pt</PaddingRight>", "<PaddingTop>1pt</PaddingTop>", "<PaddingBottom>1pt</PaddingBottom>"]
    return (f'<Textbox Name="{name}"><CanGrow>{str(can_grow).lower()}</CanGrow><KeepTogether>true</KeepTogether>'
            f"<Paragraphs><Paragraph><TextRuns><TextRun><Value>{escape(value)}</Value><Style>{''.join(style_run)}</Style></TextRun></TextRuns>"
            f"{para_style}</Paragraph></Paragraphs><rd:DefaultName>{name}</rd:DefaultName>{pos}<Style>{''.join(box_style)}</Style></Textbox>")


def cell(content, colspan=None):
    span = f"<ColSpan>{colspan}</ColSpan>" if colspan else ""
    return f"<TablixCell><CellContents>{content}{span}</CellContents></TablixCell>"


def tablix():
    n = len(COLUMNS)
    cols = "".join(f"<TablixColumn><Width>{w}in</Width></TablixColumn>" for _, w, *_ in COLUMNS)
    title = textbox("txtInstitutionName",
                    '="Quarterly supervisory return — " & Fields!institution_name.Value & " (" & Fields!institution_code.Value & ")"',
                    bold=True, size="13pt", color=DARK, border=False)
    sub = textbox("txtInstitutionDetails",
                  '=Fields!institution_type.Value & " · Lead supervisor: " & Fields!supervisory_lead.Value & " · Last 8 quarters · Red = below internal watch threshold (illustrative)"',
                  size="8.5pt", color="#595959", border=False)
    row1 = cell(title, n) + "<TablixCell />" * (n - 1)
    row2 = cell(sub, n) + "<TablixCell />" * (n - 1)
    hdr = "".join(cell(textbox(f"hdr{i}", h, bold=True, color="#FFFFFF", fill=TEAL, align="Center" if i else "Left", size="8.5pt"))
                  for i, (h, *_rest) in enumerate(COLUMNS))
    det = ""
    for i, (h, _w, val, fmt, col) in enumerate(COLUMNS):
        det += cell(textbox(f"val{i}", val, fmt=fmt, color=col or DARK, align="Right" if i else "Left"))
    rows = (f"<TablixRow><Height>0.38in</Height><TablixCells>{row1}</TablixCells></TablixRow>"
            f"<TablixRow><Height>0.3in</Height><TablixCells>{row2}</TablixCells></TablixRow>"
            f"<TablixRow><Height>0.3in</Height><TablixCells>{hdr}</TablixCells></TablixRow>"
            f"<TablixRow><Height>0.25in</Height><TablixCells>{det}</TablixCells></TablixRow>")
    col_hier = "<TablixColumnHierarchy><TablixMembers>" + "<TablixMember />" * n + "</TablixMembers></TablixColumnHierarchy>"
    static = "<TablixMember><KeepWithGroup>After</KeepWithGroup><RepeatOnNewPage>true</RepeatOnNewPage><KeepTogether>true</KeepTogether></TablixMember>"
    row_hier = ("<TablixRowHierarchy><TablixMembers><TablixMember>"
                '<Group Name="grpInstitution"><GroupExpressions><GroupExpression>=Fields!institution_code.Value</GroupExpression></GroupExpressions>'
                "<PageBreak><BreakLocation>Between</BreakLocation></PageBreak></Group>"
                "<SortExpressions><SortExpression><Value>=Fields!institution_code.Value</Value></SortExpression></SortExpressions>"
                f"<TablixMembers>{static}{static}{static}"
                '<TablixMember><Group Name="grpDetails" />'
                "<SortExpressions><SortExpression><Value>=Fields!quarter_key.Value</Value></SortExpression></SortExpressions></TablixMember>"
                "</TablixMembers></TablixMember></TablixMembers></TablixRowHierarchy>")
    return (f'<Tablix Name="tblReturn"><TablixBody><TablixColumns>{cols}</TablixColumns><TablixRows>{rows}</TablixRows></TablixBody>'
            f"{col_hier}{row_hier}<DataSetName>dsReturn</DataSetName>"
            "<NoRowsMessage>No data for the selected institution(s).</NoRowsMessage>"
            f"<Top>0in</Top><Left>0in</Left><Height>1.23in</Height><Width>{BODY_WIDTH}in</Width>"
            "<Style><Border><Style>None</Style></Border></Style></Tablix>")


def fields(spec):
    return "<Fields>" + "".join(
        f'<Field Name="{n}"><DataField>{escape(d)}</DataField><rd:TypeName>{t}</rd:TypeName></Field>' for n, d, t in spec) + "</Fields>"


def dataset(name, dax, spec, params=""):
    return (f'<DataSet Name="{name}"><Query><DataSourceName>sm_fda_supervisory</DataSourceName>{params}'
            f"<CommandText>{escape(dax)}</CommandText><rd:UseGenericDesigner>true</rd:UseGenericDesigner></Query>{fields(spec)}</DataSet>")


def build() -> str:
    qp = ('<QueryParameters><QueryParameter Name="InstitutionList">'
          "<Value>=Join(Parameters!Institution.Value, \"|\")</Value></QueryParameter></QueryParameters>")
    note = textbox("txtNote", "Ratios = sum of components / sum of exposures from sm_fda_supervisory. Watch thresholds are internal and illustrative, not OSFI regulatory minimums. "
                   + BANNER + ".", size="7.5pt", color="#595959", top=1.35, left=0, height=0.3, width=BODY_WIDTH, border=False)
    # Page header repeats the institution title of the group on the current page (body textbox txtInstitutionName).
    header = textbox("txtPageHeader", '="Supervision Analytics · " & ReportItems!txtInstitutionName.Value',
                     size="8pt", color="#595959", top=0.1, left=0, height=0.25, width=BODY_WIDTH, border=False, can_grow=False)
    rule = ('<Line Name="lnHeader"><Top>0.4in</Top><Left>0in</Left><Height>0in</Height>'
            f"<Width>{BODY_WIDTH}in</Width><Style><Border><Color>{TEAL}</Color><Style>Solid</Style><Width>1.5pt</Width></Border></Style></Line>")
    footer = textbox("txtFooter", f'="{BANNER} · Page " & Globals!PageNumber & " of " & Globals!TotalPages',
                     size="8pt", color="#595959", align="Center", top=0.1, left=0, height=0.25, width=BODY_WIDTH, border=False, can_grow=False)
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<!-- {BANNER} -->
<!-- rpt_fda_institution_return: quarterly supervisory return per institution (paginated report, Letter portrait). -->
<!-- Data source: sm_fda_supervisory (Power BI semantic model). __TENANT_ID__ / __DATASET_ID__ are replaced by 01-Deploy-FdaEnvironment.ps1. -->
<!-- VERIFY: PBIDATASET connect string format; Report Builder rewrites it when you re-select the model (paginated/README-paginated.md). -->
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition" xmlns:rd="http://schemas.microsoft.com/SQLServer/reporting/reportdesigner">
  <AutoRefresh>0</AutoRefresh>
  <DataSources>
    <DataSource Name="sm_fda_supervisory">
      <ConnectionProperties>
        <DataProvider>PBIDATASET</DataProvider>
        <ConnectString>{escape(CONNECT)}</ConnectString>
      </ConnectionProperties>
      <rd:SecurityType>None</rd:SecurityType>
      <rd:DataSourceID>3f6b2a8e-1c4d-4f7a-9e2b-fda000000001</rd:DataSourceID>
    </DataSource>
  </DataSources>
  <DataSets>
    {dataset("dsInstitutions", DAX_INSTITUTIONS, FIELDS_INST)}
    {dataset("dsReturn", DAX_RETURN, FIELDS_RETURN, qp)}
  </DataSets>
  <ReportSections>
    <ReportSection>
      <Body>
        <ReportItems>
          {tablix()}
          {note}
        </ReportItems>
        <Height>1.7in</Height>
        <Style />
      </Body>
      <Width>{BODY_WIDTH}in</Width>
      <Page>
        <PageHeader>
          <Height>0.45in</Height>
          <PrintOnFirstPage>true</PrintOnFirstPage>
          <PrintOnLastPage>true</PrintOnLastPage>
          <ReportItems>
            {header}
            {rule}
          </ReportItems>
          <Style><Border><Style>None</Style></Border></Style>
        </PageHeader>
        <PageFooter>
          <Height>0.45in</Height>
          <PrintOnFirstPage>true</PrintOnFirstPage>
          <PrintOnLastPage>true</PrintOnLastPage>
          <ReportItems>
            {footer}
          </ReportItems>
          <Style><Border><Style>None</Style></Border></Style>
        </PageFooter>
        <PageHeight>11in</PageHeight>
        <PageWidth>8.5in</PageWidth>
        <LeftMargin>0.5in</LeftMargin>
        <RightMargin>0.5in</RightMargin>
        <TopMargin>0.5in</TopMargin>
        <BottomMargin>0.5in</BottomMargin>
        <Style />
      </Page>
    </ReportSection>
  </ReportSections>
  <ReportParameters>
    <ReportParameter Name="Institution">
      <DataType>String</DataType>
      <DefaultValue>
        <Values>
          <Value>FI007</Value>
        </Values>
      </DefaultValue>
      <Prompt>Institution</Prompt>
      <ValidValues>
        <DataSetReference>
          <DataSetName>dsInstitutions</DataSetName>
          <ValueField>code</ValueField>
          <LabelField>label</LabelField>
        </DataSetReference>
      </ValidValues>
      <MultiValue>true</MultiValue>
    </ReportParameter>
  </ReportParameters>
  <ReportParametersLayout>
    <GridLayoutDefinition>
      <NumberOfColumns>1</NumberOfColumns>
      <NumberOfRows>1</NumberOfRows>
      <CellDefinitions>
        <CellDefinition>
          <ColumnIndex>0</ColumnIndex>
          <RowIndex>0</RowIndex>
          <ParameterName>Institution</ParameterName>
        </CellDefinition>
      </CellDefinitions>
    </GridLayoutDefinition>
  </ReportParametersLayout>
  <Language>en-US</Language>
  <ConsumeContainerWhitespace>true</ConsumeContainerWhitespace>
  <rd:ReportUnitType>Inch</rd:ReportUnitType>
  <rd:ReportID>8d2c4e6f-7a1b-4c3d-9e5f-fda000000002</rd:ReportID>
</Report>
"""
    return xml


if __name__ == "__main__":
    path = os.path.join(HERE, "rpt_fda_institution_return.rdl")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(build())
    print("wrote", path)
