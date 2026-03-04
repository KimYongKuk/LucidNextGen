import type { WorkBook, WorkSheet, CellObject, Range } from "xlsx";
import { utils } from "xlsx";

/**
 * SheetJS WorkBook → Univer IWorkbookData 변환
 *
 * Univer의 IWorkbookData 형식:
 * {
 *   id: string,
 *   sheetOrder: string[],
 *   sheets: { [sheetId]: IWorksheetData }
 * }
 *
 * IWorksheetData:
 * {
 *   id: string, name: string,
 *   cellData: { [row]: { [col]: ICellData } },
 *   rowCount: number, columnCount: number,
 *   defaultColumnWidth: number, defaultRowHeight: number,
 *   columnData: { [col]: { w: number } },
 *   rowData: { [row]: { h: number } },
 *   mergeData: Array<{ startRow, startColumn, endRow, endColumn }>
 * }
 */

interface UniverCellData {
  v?: string | number | boolean;
  t?: number; // Univer CellValueType: 1=string, 2=number, 3=boolean, 4=force string
  f?: string; // formula (e.g., "=SUM(A1:A10)")
}

interface UniverMergeData {
  startRow: number;
  startColumn: number;
  endRow: number;
  endColumn: number;
}

interface UniverSheetData {
  id: string;
  name: string;
  cellData: Record<number, Record<number, UniverCellData>>;
  rowCount: number;
  columnCount: number;
  defaultColumnWidth: number;
  defaultRowHeight: number;
  columnData?: Record<number, { w: number }>;
  rowData?: Record<number, { h: number }>;
  mergeData?: UniverMergeData[];
}

interface UniverWorkbookData {
  id: string;
  sheetOrder: string[];
  sheets: Record<string, UniverSheetData>;
}

function convertCellValue(cell: CellObject): UniverCellData {
  const result: UniverCellData = {};

  // Handle formula (SheetJS stores without "=", Univer expects with "=")
  if ((cell as any).f) {
    result.f = `=${(cell as any).f}`;
  }

  if (cell.t === "n") {
    result.v = cell.v as number;
    result.t = 2; // number
  } else if (cell.t === "b") {
    result.v = cell.v as boolean;
    result.t = 3; // boolean
  } else if (cell.t === "s") {
    result.v = cell.v as string;
    result.t = 1; // string
  } else if (cell.t === "d") {
    // date → string representation
    result.v = cell.w || String(cell.v);
    result.t = 1;
  } else if (cell.t === "e") {
    // error
    result.v = cell.w || "#ERROR!";
    result.t = 1;
  } else if (cell.v !== undefined && cell.v !== null) {
    result.v = String(cell.v);
    result.t = 1;
  }

  return result;
}

function convertSheet(sheet: WorkSheet, sheetName: string, index: number): UniverSheetData {
  const sheetId = `sheet_${index}`;

  // Get sheet range
  const ref = sheet["!ref"];
  if (!ref) {
    return {
      id: sheetId,
      name: sheetName,
      cellData: {},
      rowCount: 100,
      columnCount: 26,
      defaultColumnWidth: 88,
      defaultRowHeight: 24,
    };
  }

  const range: Range = utils.decode_range(ref);
  const rowCount = Math.max(range.e.r + 2, 100); // +2 for padding, min 100
  const columnCount = Math.max(range.e.c + 2, 26); // min 26 (A-Z)

  // Convert cell data
  const cellData: Record<number, Record<number, UniverCellData>> = {};

  for (let r = range.s.r; r <= range.e.r; r++) {
    for (let c = range.s.c; c <= range.e.c; c++) {
      const cellRef = utils.encode_cell({ r, c });
      const cell = sheet[cellRef] as CellObject | undefined;

      if (cell && (cell.v !== undefined && cell.v !== null || (cell as any).f)) {
        if (!cellData[r]) cellData[r] = {};
        cellData[r][c] = convertCellValue(cell);
      }
    }
  }

  // Convert column widths
  const columnData: Record<number, { w: number }> = {};
  if (sheet["!cols"]) {
    sheet["!cols"].forEach((col, idx) => {
      if (col && col.wpx) {
        columnData[idx] = { w: col.wpx };
      } else if (col && col.wch) {
        // Approximate: 1 char ≈ 8px
        columnData[idx] = { w: Math.round(col.wch * 8) };
      }
    });
  }

  // Convert row heights
  const rowData: Record<number, { h: number }> = {};
  if (sheet["!rows"]) {
    sheet["!rows"].forEach((row, idx) => {
      if (row && row.hpx) {
        rowData[idx] = { h: row.hpx };
      } else if (row && row.hpt) {
        // Points to pixels: 1pt ≈ 1.333px
        rowData[idx] = { h: Math.round(row.hpt * 1.333) };
      }
    });
  }

  // Convert merged cells
  const mergeData: UniverMergeData[] = [];
  if (sheet["!merges"]) {
    for (const merge of sheet["!merges"]) {
      mergeData.push({
        startRow: merge.s.r,
        startColumn: merge.s.c,
        endRow: merge.e.r,
        endColumn: merge.e.c,
      });
    }
  }

  return {
    id: sheetId,
    name: sheetName,
    cellData,
    rowCount,
    columnCount,
    defaultColumnWidth: 88,
    defaultRowHeight: 24,
    ...(Object.keys(columnData).length > 0 && { columnData }),
    ...(Object.keys(rowData).length > 0 && { rowData }),
    ...(mergeData.length > 0 && { mergeData }),
  };
}

function isSheetEmpty(sheet: WorkSheet): boolean {
  const ref = sheet["!ref"];
  if (!ref) return true;
  const range: Range = utils.decode_range(ref);
  for (let r = range.s.r; r <= range.e.r; r++) {
    for (let c = range.s.c; c <= range.e.c; c++) {
      const cell = sheet[utils.encode_cell({ r, c })] as CellObject | undefined;
      if (cell && (cell.v !== undefined && cell.v !== null || (cell as any).f)) {
        return false;
      }
    }
  }
  return true;
}

export function sheetJsToUniverData(workbook: WorkBook): UniverWorkbookData {
  const sheetOrder: string[] = [];
  const sheets: Record<string, UniverSheetData> = {};

  // Filter out empty sheets when there are multiple sheets
  // (e.g., LLM creates data in "매출현황" but leaves default "Sheet" empty)
  const nonEmptyNames = workbook.SheetNames.filter(
    (name) => !isSheetEmpty(workbook.Sheets[name])
  );
  const sheetNames =
    nonEmptyNames.length > 0 ? nonEmptyNames : workbook.SheetNames;

  sheetNames.forEach((sheetName, index) => {
    const sheet = workbook.Sheets[sheetName];
    const sheetId = `sheet_${index}`;
    sheetOrder.push(sheetId);
    sheets[sheetId] = convertSheet(sheet, sheetName, index);
  });

  return {
    id: "workbook_1",
    sheetOrder,
    sheets,
  };
}
