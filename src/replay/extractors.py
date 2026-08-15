
from __future__ import annotations
from src.capability.artifact import TableCellExtractor
from src.surface.browser import BrowserSurface

async def extract_table_cell(surface: BrowserSurface, extractor: TableCellExtractor) -> str:
    page = surface.page
    tables = page.locator("table")
    count = await tables.count()
    for i in range(count):
        table = tables.nth(i)
        text = await table.inner_text()
        if extractor.row_text not in text or extractor.column_header not in text:
            continue
        rows = table.locator("tr")
        if await rows.count() < 2:
            continue
        headers = [x.strip() for x in await rows.first.locator("th,td").all_inner_texts()]
        if extractor.column_header not in headers:
            continue
        column_index = headers.index(extractor.column_header)
        for r in range(1, await rows.count()):
            cells = [x.strip() for x in await rows.nth(r).locator("th,td").all_inner_texts()]
            if cells and cells[0] == extractor.row_text:
                if column_index >= len(cells):
                    raise LookupError("Requested output column is missing from matching row.")
                return cells[column_index]
    raise LookupError(
        f"Could not extract table cell row={extractor.row_text!r} column={extractor.column_header!r}"
    )
