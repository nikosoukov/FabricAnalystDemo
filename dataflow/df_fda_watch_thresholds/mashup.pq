// SYNTHETIC DATA · for training only · no OSFI data
// df_fda_watch_thresholds: Excel (WIDE, styled) -> LONG table supervisory_watch_thresholds.
// Internal watch thresholds (illustrative), NOT OSFI regulatory minimums.
// 01-Deploy-FdaEnvironment.ps1 replaces __WORKSPACE_ID__ and __LAKEHOUSE_ID__ (FDA-Analyst-Dev / lh_supervisory).
// The data destination (lh_supervisory > existing table supervisory_watch_thresholds > Replace) is set by click (README D5).
// VERIFY: Lakehouse.Contents navigation keys (workspaceId, lakehouseId, Id = "Files") match what Get data > Lakehouse generates
//         in your tenant. If not, rebuild the Source steps with the UI (dataflow/click-build.md) and keep the steps from SkipTitleRows on.
section Section1;

shared supervisory_watch_thresholds = let
    Source = Lakehouse.Contents(null),
    Workspace = Source{[workspaceId = "__WORKSPACE_ID__"]}[Data],
    Lakehouse = Workspace{[lakehouseId = "__LAKEHOUSE_ID__"]}[Data],
    Files = Lakehouse{[Id = "Files", ItemKind = "Folder"]}[Data],
    ReferenceFolder = Files{[Name = "reference"]}[Content],
    // v1 = supervisory_watch_thresholds.xlsx, v2 = supervisory_watch_thresholds_v2.xlsx: the highest name wins
    Candidates = Table.SelectRows(ReferenceFolder, each Text.StartsWith([Name], "supervisory_watch_thresholds") and Text.EndsWith([Name], ".xlsx")),
    LatestFile = Table.First(Table.Sort(Candidates, {{"Name", Order.Descending}})),
    Workbook = Excel.Workbook(LatestFile[Content], null, true),
    Sheet = Workbook{[Item = "Watch thresholds", Kind = "Sheet"]}[Data],
    // rows 1-3 = title, "Last reviewed", blank; row 4 = headers
    SkipTitleRows = Table.Skip(Sheet, 3),
    PromotedHeaders = Table.PromoteHeaders(SkipTitleRows, [PromoteAllScalars = true]),
    Unpivoted = Table.UnpivotOtherColumns(PromotedHeaders, {"institution_type", "effective_from_quarter"}, "metric", "watch_threshold"),
    RemovedNulls = Table.SelectRows(Unpivoted, each [institution_type] <> null and [watch_threshold] <> null and [watch_threshold] <> ""),
    ChangedTypes = Table.TransformColumnTypes(RemovedNulls, {
        {"institution_type", type text},
        {"metric", type text},
        {"watch_threshold", type number},
        {"effective_from_quarter", Int64.Type}
    }),
    AddedSourceFile = Table.AddColumn(ChangedTypes, "source_file", each LatestFile[Name], type text),
    Result = Table.SelectColumns(AddedSourceFile, {"institution_type", "metric", "watch_threshold", "effective_from_quarter", "source_file"})
in
    Result;
