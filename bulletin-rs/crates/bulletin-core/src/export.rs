//! Exports Excel (feuilles professeurs, totalisations, moyennes).
//!
//! L'export PDF du compte rendu est prévu dans un module séparé afin de
//! ne pas alourdir le cœur de calcul.

use crate::calc::{compute_annuelle, compute_stats, compute_totalisation, compute_trimestre};
use crate::db::Database;
use crate::models::{AnnualRow, Subject, Totalisation, TrimRow, fmt_note};
use crate::sync::label_for_exam;
use anyhow::{Context, Result};
use rust_xlsxwriter::{Color, Format, Workbook};
use std::fs;
use std::path::{Path, PathBuf};

const HEADER_COLOR: Color = Color::RGB(0x1F3A5F);

fn header_format() -> Format {
    Format::new()
        .set_bold()
        .set_font_color(Color::White)
        .set_background_color(HEADER_COLOR)
        .set_align(rust_xlsxwriter::FormatAlign::Center)
        .set_border(rust_xlsxwriter::FormatBorder::Thin)
}

fn title_format() -> Format {
    Format::new().set_bold().set_font_size(14)
}

fn subtitle_format() -> Format {
    Format::new()
        .set_italic()
        .set_font_color(Color::RGB(0x5B6472))
}

fn safe_file_name(name: &str) -> String {
    name.chars()
        .map(|c| {
            if c.is_alphanumeric() || matches!(c, ' ' | '-' | '_' | '.') {
                c
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim()
        .to_string()
}

/// Exporte une matière au format « feuille professeur ».
pub fn export_subject_xlsx(db: &Database, subject: &Subject, path: &Path) -> Result<PathBuf> {
    let students = db.list_students()?;
    let nb_exams = db.get_setting_int("nb_examens", 6).clamp(1, 6);

    let mut workbook = Workbook::new();
    let sheet = workbook.add_worksheet();
    let sheet_name: String = subject.name.chars().take(31).collect();
    sheet.set_name(if sheet_name.is_empty() {
        "Matière"
    } else {
        &sheet_name
    })?;

    sheet.write_string_with_format(1, 1, &db.get_setting("etablissement", ""), &title_format())?;
    sheet.write_string_with_format(
        1,
        4,
        &format!("Matière : {}", subject.name),
        &title_format(),
    )?;
    sheet.write_string(2, 1, &format!("Classe : {}", db.get_setting("classe", "")))?;
    sheet.write_string(2, 2, &format!("Coef : {}", format_coeff(subject.coeff)))?;
    sheet.write_string(
        2,
        5,
        &format!(
            "Prof : {}",
            if subject.teacher.trim().is_empty() {
                "—"
            } else {
                &subject.teacher
            }
        ),
    )?;
    sheet.write_string_with_format(
        3,
        1,
        &format!("Année scolaire : {}", db.get_setting("annee_scolaire", "")),
        &subtitle_format(),
    )?;

    let headers = ["N°", "Nom et Prénoms"];
    let header = header_format();
    for (index, value) in headers.iter().enumerate() {
        sheet.write_string_with_format(5, index as u16, *value, &header)?;
    }
    for exam in 1..=nb_exams {
        sheet.write_string_with_format(5, (1 + exam) as u16, &label_for_exam(exam), &header)?;
    }

    for (row_index, student) in students.iter().enumerate() {
        let row = 6 + row_index as u32;
        sheet.write_number(row, 0, student.num as f64)?;
        sheet.write_string(row, 1, student.full_name())?;
        for exam in 1..=nb_exams {
            if let Some(value) = db.get_grade(student.id, subject.id, exam)? {
                sheet.write_number(row, (1 + exam) as u16, value)?;
            }
        }
    }

    sheet.set_column_width(0, 6)?;
    sheet.set_column_width(1, 32)?;
    for exam in 1..=nb_exams {
        sheet.set_column_width((1 + exam) as u16, 12)?;
    }

    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    workbook.save(path)?;
    Ok(path.to_path_buf())
}

fn format_coeff(coeff: f64) -> String {
    if coeff.fract() == 0.0 {
        format!("{coeff:.0}")
    } else {
        format!("{coeff}")
    }
}

/// Exporte toutes les feuilles de matières d'une classe.
pub fn export_all_subjects(db: &Database, out_dir: &Path) -> Result<usize> {
    std::fs::create_dir_all(out_dir)?;
    let mut count = 0;
    for subject in db.list_subjects()? {
        let name = safe_file_name(&subject.name);
        let path = out_dir.join(format!("{name}.xlsx"));
        export_subject_xlsx(db, &subject, &path)
            .with_context(|| format!("Export de la matière {}", subject.name))?;
        count += 1;
    }
    Ok(count)
}

/// Exporte une totalisation d'examen.
pub fn export_totalisation_xlsx(db: &Database, exam_num: i64, path: &Path) -> Result<PathBuf> {
    let totalisation: Totalisation = compute_totalisation(db, exam_num)?;
    let mut workbook = Workbook::new();
    let sheet = workbook.add_worksheet();
    sheet.set_name(&format!("totalisation{exam_num}"))?;

    let header = header_format();
    sheet.write_string_with_format(0, 0, "N°", &header)?;
    sheet.write_string_with_format(0, 1, "Nom et Prénoms", &header)?;
    for (index, subject) in totalisation.subjects.iter().enumerate() {
        sheet.write_string_with_format(0, (2 + index) as u16, subject.abbrev(), &header)?;
    }
    let notes_end = 2 + totalisation.subjects.len();
    sheet.write_string_with_format(0, notes_end as u16, "Tot", &header)?;
    sheet.write_string_with_format(0, (notes_end + 1) as u16, "Moy", &header)?;
    sheet.write_string_with_format(0, (notes_end + 2) as u16, "RG", &header)?;

    for (row_index, row) in totalisation.rows.iter().enumerate() {
        let sheet_row = 1 + row_index as u32;
        sheet.write_number(sheet_row, 0, row.student.num as f64)?;
        sheet.write_string(sheet_row, 1, row.student.full_name())?;
        for (index, subject) in totalisation.subjects.iter().enumerate() {
            if let Some(Some(value)) = row.notes.get(&subject.id) {
                sheet.write_number(sheet_row, (2 + index) as u16, *value)?;
            }
        }
        if row.valid {
            if let Some(total) = row.total {
                sheet.write_number(sheet_row, notes_end as u16, total)?;
            }
            if let Some(moy) = row.moy {
                sheet.write_number(sheet_row, (notes_end + 1) as u16, moy)?;
            }
            if let Some(rank) = row.rank {
                sheet.write_number(sheet_row, (notes_end + 2) as u16, rank as f64)?;
            }
        } else {
            sheet.write_string_with_format(
                sheet_row,
                notes_end as u16,
                "NC",
                &Format::new().set_font_color(Color::RGB(0x9AA4B2)),
            )?;
        }
    }

    sheet.set_column_width(0, 6)?;
    sheet.set_column_width(1, 32)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    workbook.save(path)?;
    Ok(path.to_path_buf())
}

/// Exporte les 4 tableaux de moyennes dans un dossier.
pub fn export_moyennes(db: &Database, out_dir: &Path) -> Result<Vec<PathBuf>> {
    std::fs::create_dir_all(out_dir)?;
    let mut files = Vec::new();

    for trimestre in 1..=3 {
        let rows = compute_trimestre(db, trimestre)?;
        let headers = [
            "N°",
            "Prénoms",
            "M.J. (×1)",
            "Comp. (×2)",
            "Total M.J",
            "Total C",
            "Total/40",
            "Moyenne/20",
            "Rang",
        ];
        let mut workbook = Workbook::new();
        let sheet = workbook.add_worksheet();
        sheet.set_name(&format!("Trimestre {trimestre}"))?;
        write_headers(sheet, &headers)?;
        for (index, row) in rows.iter().enumerate() {
            write_trim_row(sheet, 1 + index as u32, row)?;
        }
        let path = out_dir.join(format!("Moyenne_T{trimestre}.xlsx"));
        workbook.save(&path)?;
        files.push(path);
    }

    let rows = compute_annuelle(db)?;
    let headers = [
        "N°",
        "Prénoms",
        "M.J.1 (×1)",
        "Comp.1 (×2)",
        "M.J.2 (×1)",
        "Comp.2 (×2)",
        "M.J.3 (×1)",
        "Comp.3 (×2)",
        "TOTAL/120",
        "MGA/20",
        "Rang",
    ];
    let mut workbook = Workbook::new();
    let sheet = workbook.add_worksheet();
    sheet.set_name("Annuelle")?;
    write_headers(sheet, &headers)?;
    for (index, row) in rows.iter().enumerate() {
        write_annual_row(sheet, 1 + index as u32, row)?;
    }
    let path = out_dir.join("Moyenne_Annuelle.xlsx");
    workbook.save(&path)?;
    files.push(path);

    Ok(files)
}

fn write_headers(sheet: &mut rust_xlsxwriter::Worksheet, headers: &[&str]) -> Result<()> {
    let header = header_format();
    for (index, value) in headers.iter().enumerate() {
        sheet.write_string_with_format(0, index as u16, *value, &header)?;
    }
    Ok(())
}

fn write_optional_number(
    sheet: &mut rust_xlsxwriter::Worksheet,
    row: u32,
    col: u16,
    value: Option<f64>,
) -> Result<()> {
    match value {
        Some(value) => {
            sheet.write_number(row, col, value)?;
        }
        None => {
            sheet.write_string_with_format(
                row,
                col,
                "NC",
                &Format::new().set_font_color(Color::RGB(0x9AA4B2)),
            )?;
        }
    }
    Ok(())
}

fn write_trim_row(sheet: &mut rust_xlsxwriter::Worksheet, row: u32, data: &TrimRow) -> Result<()> {
    sheet.write_number(row, 0, data.student.num as f64)?;
    sheet.write_string(row, 1, data.student.full_name())?;
    write_optional_number(sheet, row, 2, data.m_moy)?;
    write_optional_number(sheet, row, 3, data.c_moy)?;
    write_optional_number(sheet, row, 4, data.m_total)?;
    write_optional_number(sheet, row, 5, data.c_total)?;
    write_optional_number(sheet, row, 6, data.tot)?;
    write_optional_number(sheet, row, 7, data.moy)?;
    match data.rank {
        Some(rank) => {
            sheet.write_number(row, 8, rank as f64)?;
        }
        None => {
            sheet.write_string(row, 8, "NC")?;
        }
    }
    Ok(())
}

fn write_annual_row(
    sheet: &mut rust_xlsxwriter::Worksheet,
    row: u32,
    data: &AnnualRow,
) -> Result<()> {
    sheet.write_number(row, 0, data.student.num as f64)?;
    sheet.write_string(row, 1, data.student.full_name())?;
    write_optional_number(sheet, row, 2, data.mj1)?;
    write_optional_number(sheet, row, 3, data.co1)?;
    write_optional_number(sheet, row, 4, data.mj2)?;
    write_optional_number(sheet, row, 5, data.co2)?;
    write_optional_number(sheet, row, 6, data.mj3)?;
    write_optional_number(sheet, row, 7, data.co3)?;
    write_optional_number(sheet, row, 8, data.total)?;
    write_optional_number(sheet, row, 9, data.mga)?;
    match data.rank {
        Some(rank) => {
            sheet.write_number(row, 10, rank as f64)?;
        }
        None => {
            sheet.write_string(row, 10, "NC")?;
        }
    }
    Ok(())
}

/// Export rapide d'une grille générique (utilisé par l'UI pour les
/// totalisations et les compte rendus tabulaires).
pub fn export_grid(
    path: &Path,
    sheet_name: &str,
    headers: &[String],
    rows: &[Vec<String>],
) -> Result<PathBuf> {
    let mut workbook = Workbook::new();
    let sheet = workbook.add_worksheet();
    sheet.set_name(&sheet_name.chars().take(31).collect::<String>())?;
    let header = header_format();
    for (col, value) in headers.iter().enumerate() {
        sheet.write_string_with_format(0, col as u16, value, &header)?;
    }
    for (row_index, row) in rows.iter().enumerate() {
        for (col, value) in row.iter().enumerate() {
            if value.is_empty() {
                continue;
            }
            if let Ok(number) = value.replace(',', ".").parse::<f64>() {
                sheet.write_number(1 + row_index as u32, col as u16, number)?;
            } else {
                sheet.write_string(1 + row_index as u32, col as u16, value)?;
            }
        }
    }
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    workbook.save(path)?;
    Ok(path.to_path_buf())
}

/// Résumé texte d'un bulletin (pour l'aperçu PDF de l'UI).
pub fn student_summary(db: &Database, student_num: i64) -> Result<Option<String>> {
    let student = db
        .list_students()?
        .into_iter()
        .find(|student| student.num == student_num);
    let Some(student) = student else {
        return Ok(None);
    };
    let annual = compute_annuelle(db)?;
    let row = annual.into_iter().find(|row| row.student.id == student.id);
    let mut lines = vec![
        format!("{} — {}", student.num, student.full_name()),
        format!("MGA : {}", fmt_note(row.as_ref().and_then(|r| r.mga))),
        format!("Rang : {:?}", row.as_ref().and_then(|r| r.rank)),
    ];
    for trimestre in 1..=3 {
        let rows = compute_trimestre(db, trimestre)?;
        if let Some(row) = rows.into_iter().find(|row| row.student.id == student.id) {
            lines.push(format!(
                "T{trimestre} : {} (MJ {}, Compo {})",
                fmt_note(row.moy),
                fmt_note(row.m_moy),
                fmt_note(row.c_moy)
            ));
        }
    }
    Ok(Some(lines.join("\n")))
}

// ---------------------------------------------------------------------------
// Export PDF du compte rendu
// ---------------------------------------------------------------------------

const PDF_PAGE_W: f32 = 595.28;
const PDF_PAGE_H: f32 = 841.89;
const PDF_MARGIN: f32 = 56.7;

/// Largeurs Helvetica (unités de 1/1000 em) pour les caractères ASCII.
const HELVETICA_WIDTHS: [u16; 95] = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667,
    611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500,
    222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
];

fn char_width(ch: char) -> f32 {
    let code = ch as u32;
    if (0x20..=0x7E).contains(&code) {
        HELVETICA_WIDTHS[(code - 0x20) as usize] as f32 / 1000.0
    } else if code >= 0xA0 && code <= 0xFF {
        0.556
    } else {
        0.5
    }
}

fn text_width(text: &str, size: f32, bold: bool) -> f32 {
    let base: f32 = text.chars().map(char_width).sum();
    base * size * if bold { 1.03 } else { 1.0 }
}

/// Encode en WinAnsi (CP1252) avec échappement des chaînes littérales PDF.
fn pdf_string(text: &str) -> Vec<u8> {
    let mut out = Vec::with_capacity(text.len());
    for ch in text.chars() {
        let byte = match ch {
            '\u{20AC}' => 0x80,
            '\u{201A}' => 0x82,
            '\u{0192}' => 0x83,
            '\u{201E}' => 0x84,
            '\u{2026}' => 0x85,
            '\u{2020}' => 0x86,
            '\u{2021}' => 0x87,
            '\u{02C6}' => 0x88,
            '\u{2030}' => 0x89,
            '\u{0160}' => 0x8A,
            '\u{2039}' => 0x8B,
            '\u{0152}' => 0x8C,
            '\u{017D}' => 0x8E,
            '\u{2018}' => 0x91,
            '\u{2019}' => 0x92,
            '\u{201C}' => 0x93,
            '\u{201D}' => 0x94,
            '\u{2022}' => 0x95,
            '\u{2013}' => 0x96,
            '\u{2014}' => 0x97,
            '\u{02DC}' => 0x98,
            '\u{2122}' => 0x99,
            '\u{0161}' => 0x9A,
            '\u{203A}' => 0x9B,
            '\u{0153}' => 0x9C,
            '\u{017E}' => 0x9E,
            '\u{0178}' => 0x9F,
            '\n' | '\r' | '\t' => b' ',
            ch if (ch as u32) < 0x80 => ch as u8,
            ch if (ch as u32) <= 0xFF => ch as u8,
            _ => b'?',
        };
        match byte {
            b'(' | b')' | b'\\' => {
                out.push(b'\\');
                out.push(byte);
            }
            _ => out.push(byte),
        }
    }
    out
}

fn fit_text(text: &str, max_width: f32, size: f32, bold: bool) -> String {
    if text_width(text, size, bold) <= max_width {
        return text.to_string();
    }
    let mut out = String::new();
    for ch in text.chars() {
        let mut candidate = out.clone();
        candidate.push(ch);
        candidate.push('…');
        if text_width(&candidate, size, bold) > max_width {
            break;
        }
        out.push(ch);
    }
    out.push('…');
    out
}

/// Petit générateur PDF (A4, polices Helvetica base-14) sans dépendance externe.
struct PdfDoc {
    pages: Vec<Vec<u8>>,
    current: Vec<u8>,
    y: f32,
    started: bool,
}

impl PdfDoc {
    fn new() -> Self {
        Self {
            pages: Vec::new(),
            current: Vec::new(),
            y: PDF_MARGIN,
            started: false,
        }
    }

    fn finish_page(&mut self) {
        if !self.started {
            return;
        }
        let page_no = self.pages.len() + 1;
        let label = format!("Page {page_no}");
        self.text_at(
            PDF_PAGE_W - PDF_MARGIN - text_width(&label, 8.0, false),
            PDF_PAGE_H - 28.0,
            &label,
            8.0,
            false,
            [0.45, 0.45, 0.45],
        );
        self.pages.push(std::mem::take(&mut self.current));
        self.started = false;
    }

    fn start_page(&mut self) {
        self.finish_page();
        self.current.clear();
        self.y = PDF_MARGIN;
        self.started = true;
    }

    fn ensure_room(&mut self, height: f32) {
        if self.y + height > PDF_PAGE_H - PDF_MARGIN - 14.0 {
            self.start_page();
        }
    }

    fn fill_rect(&mut self, x: f32, top: f32, w: f32, h: f32, gray: f32) {
        let y = PDF_PAGE_H - (top + h);
        self.current.extend(
            format!("{gray:.3} {gray:.3} {gray:.3} rg {x:.2} {y:.2} {w:.2} {h:.2} re f\n")
                .as_bytes(),
        );
    }

    fn stroke_rect(&mut self, x: f32, top: f32, w: f32, h: f32) {
        let y = PDF_PAGE_H - (top + h);
        self.current.extend(
            format!("0.55 0.58 0.62 RG 0.5 w {x:.2} {y:.2} {w:.2} {h:.2} re S\n").as_bytes(),
        );
    }

    fn text_at(&mut self, x: f32, top: f32, text: &str, size: f32, bold: bool, rgb: [f32; 3]) {
        if text.is_empty() {
            return;
        }
        let baseline = PDF_PAGE_H - (top + size * 0.82);
        let font = if bold { "F2" } else { "F1" };
        self.current.extend(
            format!(
                "{} {} {} rg BT /{} {:.2} Tf {:.2} {:.2} Td (",
                rgb[0], rgb[1], rgb[2], font, size, x, baseline
            )
            .as_bytes(),
        );
        self.current.extend(pdf_string(text));
        self.current.extend(b") Tj ET\n");
    }

    fn text_centered(&mut self, top: f32, text: &str, size: f32, bold: bool, rgb: [f32; 3]) {
        let x = (PDF_PAGE_W - text_width(text, size, bold)) / 2.0;
        self.text_at(x, top, text, size, bold, rgb);
    }

    fn table_row(
        &mut self,
        x: f32,
        widths: &[f32],
        cells: &[String],
        size: f32,
        header: bool,
        row_h: f32,
    ) {
        let mut cx = x;
        for (index, width) in widths.iter().enumerate() {
            if header {
                self.fill_rect(cx, self.y, *width, row_h, 0.90);
            }
            self.stroke_rect(cx, self.y, *width, row_h);
            let text = cells.get(index).map(String::as_str).unwrap_or("");
            let available = (width - 8.0).max(4.0);
            let fitted = fit_text(text, available, size, header);
            let text_top = self.y + (row_h - size) / 2.0 + 2.0;
            if index == 0 {
                self.text_at(
                    cx + 4.0,
                    text_top,
                    &fitted,
                    size,
                    header,
                    [0.12, 0.15, 0.20],
                );
            } else {
                let tx = cx + (width - text_width(&fitted, size, header)) / 2.0;
                self.text_at(tx, text_top, &fitted, size, header, [0.12, 0.15, 0.20]);
            }
            cx += width;
        }
        self.y += row_h;
    }

    fn table(
        &mut self,
        x: f32,
        widths: &[f32],
        header: &[String],
        rows: &[Vec<String>],
        size: f32,
    ) {
        let row_h = size * 1.35 + 7.0;
        self.ensure_room(row_h * 2.0);
        self.table_row(x, widths, header, size, true, row_h);
        for row in rows {
            if self.y + row_h > PDF_PAGE_H - PDF_MARGIN - 14.0 {
                self.start_page();
                self.table_row(x, widths, header, size, true, row_h);
            }
            self.table_row(x, widths, row, size, false, row_h);
        }
    }

    fn build(self) -> Vec<u8> {
        let page_count = self.pages.len();
        let mut objects: Vec<Vec<u8>> = Vec::new();
        objects.push(b"<< /Type /Catalog /Pages 2 0 R >>".to_vec());
        let kids: Vec<String> = (0..page_count)
            .map(|index| format!("{} 0 R", 5 + index * 2))
            .collect();
        objects.push(
            format!(
                "<< /Type /Pages /Kids [{}] /Count {page_count} >>",
                kids.join(" ")
            )
            .into_bytes(),
        );
        objects.push(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
                .to_vec(),
        );
        objects.push(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
                .to_vec(),
        );
        for (index, content) in self.pages.iter().enumerate() {
            let content_obj = 6 + index * 2;
            objects.push(
                format!(
                    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PDF_PAGE_W:.2} {PDF_PAGE_H:.2}] \
                     /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_obj} 0 R >>"
                )
                .into_bytes(),
            );
            let mut stream = format!("<< /Length {} >>\nstream\n", content.len()).into_bytes();
            stream.extend_from_slice(content);
            stream.extend_from_slice(b"\nendstream");
            objects.push(stream);
        }

        let mut out: Vec<u8> = Vec::new();
        out.extend_from_slice(b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
        let mut offsets = Vec::with_capacity(objects.len());
        for (index, object) in objects.iter().enumerate() {
            offsets.push(out.len());
            out.extend_from_slice(format!("{} 0 obj\n", index + 1).as_bytes());
            out.extend_from_slice(object);
            out.extend_from_slice(b"\nendobj\n");
        }
        let xref_offset = out.len();
        out.extend_from_slice(format!("xref\n0 {}\n", objects.len() + 1).as_bytes());
        out.extend_from_slice(b"0000000000 65535 f \n");
        for offset in offsets {
            out.extend_from_slice(format!("{offset:010} 00000 n \n").as_bytes());
        }
        out.extend_from_slice(
            format!(
                "trailer\n<< /Size {} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n",
                objects.len() + 1
            )
            .as_bytes(),
        );
        out
    }
}

fn pdf_avg(value: Option<f64>) -> String {
    match value {
        Some(value) => format!("{value:.2}"),
        None => "NC".to_string(),
    }
}

/// Exporte le compte rendu des trois trimestres au format PDF.
///
/// Reproduit la mise en page de l'application Python : un tableau général et
/// un tableau « élèves ≥ 10/20 par matière » pour chaque trimestre.
pub fn export_report_pdf(db: &Database, _trimestre: i64, path: &Path) -> Result<PathBuf> {
    let subjects = db.list_subjects()?;
    let etablissement = db.get_setting("etablissement", "");
    let classe = db.get_setting("classe", "");
    let annee = db.get_setting("annee_scolaire", "");

    let mut doc = PdfDoc::new();
    doc.start_page();

    doc.text_centered(
        PDF_MARGIN,
        if etablissement.trim().is_empty() {
            "Bulletin"
        } else {
            &etablissement
        },
        18.0,
        true,
        [0.09, 0.13, 0.20],
    );
    doc.y = PDF_MARGIN + 28.0;
    doc.text_centered(
        doc.y,
        "COMPTE RENDU TRIMESTRES",
        13.0,
        true,
        [0.12, 0.16, 0.23],
    );
    doc.y += 20.0;
    doc.text_centered(
        doc.y,
        &format!("Classe : {classe} — Année : {annee}"),
        10.0,
        false,
        [0.25, 0.29, 0.36],
    );
    doc.y += 26.0;

    let widths = [180.0, 100.0, 100.0, 100.0];

    for t in 1..=3 {
        let n_mj = 2 * t - 1;
        let n_co = 2 * t;
        let stats_mj = compute_stats(db, n_mj)?;
        let stats_co = compute_stats(db, n_co)?;
        let lbl_mj = label_for_exam(n_mj);
        let lbl_co = label_for_exam(n_co);

        doc.ensure_room(52.0);
        doc.text_at(
            PDF_MARGIN,
            doc.y,
            &format!("Trimestre {t} — {lbl_mj} + {lbl_co}"),
            12.0,
            true,
            [0.09, 0.13, 0.20],
        );
        doc.y += 22.0;

        let ensemble = match (stats_mj.moyenne_classe, stats_co.moyenne_classe) {
            (Some(a), Some(b)) => Some((a + b) / 2.0),
            (mj, co) => mj.filter(|value| *value != 0.0).or(co),
        };
        let general = vec![
            vec![
                "Effectif".to_string(),
                stats_mj.effectif.to_string(),
                stats_co.effectif.to_string(),
                stats_mj.effectif.to_string(),
            ],
            vec![
                "Classés".to_string(),
                stats_mj.classes.to_string(),
                stats_co.classes.to_string(),
                stats_mj.classes.max(stats_co.classes).to_string(),
            ],
            vec![
                "Moyenne classe".to_string(),
                pdf_avg(stats_mj.moyenne_classe),
                pdf_avg(stats_co.moyenne_classe),
                pdf_avg(ensemble),
            ],
        ];
        doc.table(
            PDF_MARGIN,
            &widths,
            &[
                "Indicateur".to_string(),
                lbl_mj.clone(),
                lbl_co.clone(),
                "Ensemble".to_string(),
            ],
            &general,
            9.0,
        );
        doc.y += 14.0;

        doc.ensure_room(34.0);
        doc.text_at(
            PDF_MARGIN,
            doc.y,
            "Élèves ≥ 10/20 par matière",
            10.0,
            true,
            [0.09, 0.13, 0.20],
        );
        doc.y += 17.0;

        let rows: Vec<Vec<String>> = subjects
            .iter()
            .map(|subject| {
                let nb_mj = stats_mj
                    .nb_above_avg_per_subject
                    .get(&subject.id)
                    .copied()
                    .unwrap_or(0);
                let nb_co = stats_co
                    .nb_above_avg_per_subject
                    .get(&subject.id)
                    .copied()
                    .unwrap_or(0);
                vec![
                    subject.name.clone(),
                    nb_mj.to_string(),
                    nb_co.to_string(),
                    nb_mj.max(nb_co).to_string(),
                ]
            })
            .collect();
        doc.table(
            PDF_MARGIN,
            &widths,
            &[
                "Matière".to_string(),
                lbl_mj,
                lbl_co,
                "Ensemble".to_string(),
            ],
            &rows,
            8.5,
        );
        doc.y += 20.0;
    }

    doc.finish_page();
    let bytes = doc.build();
    fs::write(path, bytes).with_context(|| format!("écriture du PDF {}", path.display()))?;
    Ok(path.to_path_buf())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::Database;

    #[test]
    fn export_subject_produces_a_file() {
        let db = Database::open_in_memory().unwrap();
        db.add_student(1, "Rakoto", "Jean", "", "", "").unwrap();
        let subject = db.list_subjects().unwrap().remove(0);
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("test.xlsx");
        export_subject_xlsx(&db, &subject, &path).unwrap();
        assert!(path.exists());
        assert!(std::fs::metadata(&path).unwrap().len() > 1000);
    }

    #[test]
    fn export_grid_writes_values() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("grid.xlsx");
        export_grid(
            &path,
            "Test",
            &["A".into(), "B".into()],
            &[vec!["1".into(), "deux".into()]],
        )
        .unwrap();
        assert!(path.exists());
    }

    #[test]
    fn export_report_pdf_produces_valid_pdf() {
        let db = Database::open_in_memory().unwrap();
        let subject = db.list_subjects().unwrap().remove(0);
        let student_id = db.add_student(1, "Rakoto", "Jean", "", "", "").unwrap();
        db.set_grade(student_id, subject.id, 1, Some(12.0)).unwrap();
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cr.pdf");
        export_report_pdf(&db, 1, &path).unwrap();
        let bytes = std::fs::read(&path).unwrap();
        assert!(bytes.starts_with(b"%PDF"));
        assert!(bytes.ends_with(b"%%EOF\n"));
        assert!(bytes.len() > 2000);
        let text = String::from_utf8_lossy(&bytes);
        assert!(text.contains("COMPTE RENDU TRIMESTRES"));
        assert!(text.contains("Trimestre 1"));
        assert!(text.contains("Trimestre 3"));
    }
}
