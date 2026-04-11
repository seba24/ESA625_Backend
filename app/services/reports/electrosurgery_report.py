# -*- coding: utf-8 -*-
"""
Generador de Reportes PDF para Electrobisturi (ESU)
Genera reportes profesionales de pruebas de electrobisturi segun IEC 60601-2-2

Hereda de BaseReportGenerator para mantener formato consistente.
"""

import io
import os
import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

import sys
try:
    from app.services.reports.base_report_generator import BaseReportGenerator
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from app.services.reports.base_report_generator import BaseReportGenerator

log = logging.getLogger(__name__)


class ESUReportGenerator(BaseReportGenerator):
    """Generador de reportes PDF para pruebas de electrobisturi."""

    MODULE_NAME = "ELECTROBISTURÍ"
    MODULE_TITLE = "VALIDACIÓN TRAZABLE — ELECTROBISTURÍ"
    MODULE_SUBTITLE = "Analizador de Unidad Electroquirurgica"
    MODULE_STANDARD = "IEC 60601-2-2"

    def __init__(self):
        super().__init__()

    def _create_pdf_document(self, buffer: io.BytesIO):
        """Crear documento con primera pagina portrait y resto landscape."""
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate
        from reportlab.lib.units import inch

        portrait_size = letter  # 612 x 792
        landscape_size = landscape(letter)  # 792 x 612

        doc = BaseDocTemplate(
            buffer,
            pagesize=portrait_size,
            leftMargin=0.5*inch,
            rightMargin=0.5*inch,
            topMargin=1.2*inch,
            bottomMargin=0.6*inch,
        )

        # Frame portrait (pagina 1)
        frame_portrait = Frame(
            0.5*inch, 0.6*inch,
            portrait_size[0] - 1.0*inch,
            portrait_size[1] - 1.8*inch,
            id='portrait'
        )

        # Frame landscape (paginas 2+)
        frame_landscape = Frame(
            0.5*inch, 0.6*inch,
            landscape_size[0] - 1.0*inch,
            landscape_size[1] - 1.8*inch,
            id='landscape'
        )

        template_portrait = PageTemplate(
            id='portrait',
            frames=frame_portrait,
            onPage=self._create_header,
            pagesize=portrait_size,
        )
        template_landscape = PageTemplate(
            id='landscape',
            frames=frame_landscape,
            onPage=self._create_header_landscape,
            pagesize=landscape_size,
        )

        doc.addPageTemplates([template_portrait, template_landscape])
        return doc

    def _create_header_landscape(self, canvas_obj, doc):
        """Encabezado y pie de pagina adaptado a formato apaisado (landscape)."""
        from reportlab.lib import colors

        page_width = 792   # landscape letter width
        page_height = 612  # landscape letter height
        header_h = 62
        header_y = page_height - header_h  # 550

        canvas_obj.saveState()

        # Barra de encabezado azul oscuro
        canvas_obj.setFillColor(self.COLOR_PRIMARIO)
        canvas_obj.rect(0, header_y, page_width, header_h, fill=True, stroke=False)

        # Linea decorativa azul
        canvas_obj.setStrokeColor(self.COLOR_SECUNDARIO)
        canvas_obj.setLineWidth(3)
        canvas_obj.line(30, header_y - 5, page_width - 30, header_y - 5)

        # Titulo principal (blanco)
        canvas_obj.setFillColor(colors.white)
        canvas_obj.setFont("Helvetica-Bold", 16)
        canvas_obj.drawString(40, header_y + 25, self.MODULE_TITLE)

        # Subtitulo con norma
        canvas_obj.setFont("Helvetica", 10)
        canvas_obj.drawString(40, header_y + 10, f"{self.MODULE_SUBTITLE} - {self.MODULE_STANDARD}")

        # Logo si existe
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                canvas_obj.drawImage(
                    self.logo_path, page_width - 170, header_y + 5,
                    width=120, height=50,
                    preserveAspectRatio=True,
                    mask='auto'
                )
            except Exception as e:
                log.warning(f"Error cargando logo: {e}")

        # Pie de pagina
        canvas_obj.setFillColor(self.COLOR_GRIS_CLARO)
        canvas_obj.rect(0, 0, page_width, 30, fill=True, stroke=False)

        canvas_obj.setStrokeColor(self.COLOR_SECUNDARIO)
        canvas_obj.setLineWidth(2)
        canvas_obj.line(30, 35, page_width - 30, 35)

        canvas_obj.setFillColor(self.COLOR_GRIS_MEDIO)
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawString(40, 15, f"ESA620 - {self.MODULE_SUBTITLE}")
        canvas_obj.drawString(380, 15, f"Generado: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")

        canvas_obj.restoreState()

    def generate_report(self,
                       results_data: Dict[str, Any],
                       output_path: Optional[str] = None) -> Optional[str]:
        """Generar reporte PDF de resultados de electrobisturi."""
        try:
            from reportlab.platypus import PageBreak
        except ImportError as e:
            log.error(f"Dependencia no instalada: {e}")
            return None

        self._init_colors_and_styles()
        self.elements = []

        results = results_data.get('results', {})
        client_info = results_data.get('client', {})
        equipment_info = results_data.get('equipment', {})

        protocol = results_data.get('protocol', {})
        if isinstance(protocol, dict):
            if protocol.get('company_name'):
                self.company_name = protocol['company_name']
            if protocol.get('logo_path') and os.path.exists(protocol.get('logo_path', '')):
                self.logo_path = protocol['logo_path']

        passed = results.get('passed_tests', 0)
        failed = results.get('failed_tests', 0)
        total = results.get('total_tests', 0)
        skipped = max(0, total - passed - failed)
        overall_status = results.get('overall_status', '')
        test_passed = overall_status in ('pass', 'completed_successfully')

        # ========== PRIMERA PAGINA ==========
        protocol_name = results.get('protocol_name', 'Protocolo ESU')
        self._add_title_section(protocol_name, test_passed)
        self._add_client_section(client_info)
        self._add_equipment_section(equipment_info, "DATOS DEL EQUIPO BAJO PRUEBA (ELECTROBISTURI)")

        self._add_execution_info_section(
            start_time=results.get('start_time'),
            protocol_name=protocol_name,
            passed=passed,
            failed=failed,
            skipped=skipped,
            overall_status='pass' if test_passed else 'fail',
        )

        analyzer_info = {
            'model': results.get('device_model', 'QA-ES II'),
            'serial': results.get('device_serial', 'N/A'),
        }
        self._add_analyzer_section(analyzer_info, "ANALIZADOR UTILIZADO")

        self._add_signature_section()

        # Cambiar a landscape para las paginas de resultados
        from reportlab.platypus import NextPageTemplate
        self.elements.append(NextPageTemplate('landscape'))
        self.elements.append(PageBreak())

        # ========== SEGUNDA PAGINA (landscape) ==========

        self._add_results_section(results)

        # Conclusiones
        conclusion_pass = (
            f"<b><font color='#10b981'>✓ EQUIPO APROBADO:</font></b> "
            f"El electrobisturi ha superado todas las pruebas ({passed}/{total}). "
            f"Los parametros medidos cumplen con IEC 60601-2-2."
        )
        conclusion_fail = (
            f"<b><font color='#ef4444'>✗ EQUIPO NO APROBADO:</font></b> "
            f"El electrobisturi presenta {failed} pruebas fuera de especificacion. "
            "Se requiere calibracion o revision del equipo."
        )
        self._add_conclusion_section(passed, failed, skipped, conclusion_pass, conclusion_fail)

        # Fotos del equipo
        photos = results_data.get('photos', [])
        if photos:
            self._add_photos_section(photos)

        # Generar PDF
        if not output_path:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            import tempfile
            output_dir = tempfile.gettempdir()
            output_path = os.path.join(output_dir, f"ESU_{protocol_name.replace(' ', '_')}_{timestamp}.pdf")

        buffer = io.BytesIO()
        doc = self._create_pdf_document(buffer)
        doc.build(self.elements)

        buffer.seek(0)
        pdf_bytes = self._add_page_numbers(buffer.getvalue())
        pdf_bytes = self._apply_pdf_security(pdf_bytes)
        pdf_bytes = self._sign_pdf(pdf_bytes)
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)

        log.info(f"Reporte de electrobisturi PDF generado: {output_path}")
        return output_path

    def _add_results_section(self, results: Dict):
        """Agregar tablas de resultados de electrobisturi, agrupados por seccion."""
        from reportlab.platypus import Paragraph, Spacer
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT

        test_results = results.get('test_results', [])

        if not test_results:
            self.elements.append(Paragraph("No hay mediciones registradas.", self.styles['Normal']))
            return

        # Inyectar rem_alarm_resistance en resultados REM para que la tabla lo use
        rem_alarm_r = results.get('rem_alarm_resistance')
        if rem_alarm_r is not None:
            for r in test_results:
                if r.get('test_type') == 'rem':
                    r['rem_alarm_resistance'] = rem_alarm_r

        # Estilo para subtitulo de seccion
        style_section_name = ParagraphStyle(
            'SectionName',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=self.COLOR_PRIMARIO,
            spaceBefore=12,
            spaceAfter=6,
            alignment=TA_LEFT,
        )

        # Verificar si hay section_name en los resultados
        has_sections = any(r.get('section_name') for r in test_results)

        if has_sections:
            # Agrupar por section_name manteniendo orden
            from collections import OrderedDict
            sections = OrderedDict()
            for r in test_results:
                sname = r.get('section_name', 'Sin seccion')
                if sname not in sections:
                    sections[sname] = []
                sections[sname].append(r)

            for section_name, section_results in sections.items():
                # Subtitulo de seccion
                self.elements.append(
                    Paragraph(f"▸ {section_name}", style_section_name)
                )

                # Dentro de la seccion, agrupar por tipo
                self._add_section_tables(section_results)
        else:
            # Protocolos antiguos: agrupar por tipo (comportamiento legacy)
            self._add_section_tables(test_results)

        # Estadisticas
        statistics = results.get('statistics', {})
        if statistics:
            self._add_statistics_table(statistics)

    def _add_section_tables(self, section_results: list):
        """Agregar tablas de resultados para un grupo de resultados (seccion o legacy)."""
        power_results = [r for r in section_results if r.get('test_type') == 'power_measurement']
        dist_results = [r for r in section_results if r.get('test_type') == 'power_distribution']
        rf_results = [r for r in section_results if r.get('test_type') == 'rf_leakage']
        rem_results = [r for r in section_results if r.get('test_type') == 'rem']

        if power_results:
            self._add_power_table(power_results)
        if dist_results:
            self._add_distribution_table(dist_results)
        if rf_results:
            self._add_rf_leakage_table(rf_results)
        if rem_results:
            self._add_rem_table(rem_results)

    def _add_power_table(self, power_results: List[Dict]):
        """Tabla de resultados de mediciones de potencia con columnas dinamicas."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("MEDICIONES DE POTENCIA", self.style_seccion))

        # Determinar columnas extras segun flags de mediciones
        has_current = any(r.get('include_current', True) and r.get('current_ma') is not None
                          for r in power_results)
        has_voltage = any(r.get('include_voltage', True) and r.get('voltage_v') is not None
                          for r in power_results)
        has_crest = any(r.get('include_crest_factor', False) and r.get('crest_factor') is not None
                        for r in power_results)

        # Construir encabezados y anchos dinamicamente (landscape = ~720pt disponibles)
        headers = ["#", "Modo", "Tipo", "Carga (Ω)", "Esperado (W)", "Medido (W)"]
        col_widths = [28, 65, 65, 60, 75, 75]

        if has_current:
            headers.append("I (mA)")
            col_widths.append(60)
        if has_voltage:
            headers.append("V (V)")
            col_widths.append(55)
        if has_crest:
            headers.append("CF")
            col_widths.append(45)

        headers.extend(["Error %", "Estado"])
        col_widths.extend([60, 40])

        data = [headers]

        for i, result in enumerate(power_results, 1):
            mode = result.get('mode', '').upper()
            etype = result.get('type', '').upper()
            resistance = result.get('resistance', 0)
            expected = result.get('expected_power', 0)
            measured = result.get('measured_power')
            error_pct = result.get('error_percent')
            status = result.get('status', '')

            measured_str = f"{measured:.2f}" if measured is not None else "-"
            error_str = f"{error_pct:+.1f}%" if error_pct is not None else "-"
            status_str = "✓" if status == 'pass' else "✗" if status == 'fail' else "—"

            row_data = [
                str(i),
                mode[:4] if mode else "-",
                etype[:4] if etype else "-",
                str(resistance),
                f"{expected:.1f}",
                measured_str,
            ]

            if has_current:
                current = result.get('current_ma')
                row_data.append(f"{current:.1f}" if current is not None else "-")
            if has_voltage:
                voltage = result.get('voltage_v')
                row_data.append(f"{voltage:.1f}" if voltage is not None else "-")
            if has_crest:
                cf = result.get('crest_factor')
                row_data.append(f"{cf:.2f}" if cf is not None else "-")

            row_data.extend([error_str, status_str])
            data.append(row_data)

        tabla = Table(data, colWidths=col_widths, hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])

        for i, result in enumerate(power_results, start=1):
            status = result.get('status', '')
            if status == 'pass':
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ACENTO)
                style.add('FONTNAME', (-1, i), (-1, i), 'Helvetica-Bold')
            elif status == 'fail':
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
                style.add('TEXTCOLOR', (0, i), (-1, i), self.COLOR_ERROR)
            elif i % 2 == 0:
                style.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

        tabla.setStyle(style)
        self.elements.append(tabla)
        self.elements.append(Spacer(1, 15))

    def _add_distribution_table(self, dist_results: List[Dict]):
        """Tabla de distribucion de potencia en funcion de la impedancia (sin evaluacion)."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph(
            "DISTRIBUCION DE POTENCIA vs IMPEDANCIA", self.style_seccion))

        # Determinar columnas extras segun flags
        has_current = any(r.get('include_current', True) and r.get('current_ma') is not None
                          for r in dist_results)
        has_voltage = any(r.get('include_voltage', True) and r.get('voltage_v') is not None
                          for r in dist_results)
        has_crest = any(r.get('include_crest_factor', False) and r.get('crest_factor') is not None
                        for r in dist_results)

        headers = ["#", "Carga (Ω)", "Config (W)", "Medido (W)"]
        col_widths = [28, 85, 85, 85]

        if has_current:
            headers.append("I (mA)")
            col_widths.append(70)
        if has_voltage:
            headers.append("V (V)")
            col_widths.append(70)
        if has_crest:
            headers.append("CF")
            col_widths.append(55)

        data = [headers]

        for i, result in enumerate(dist_results, 1):
            resistance = result.get('resistance', 0)
            expected = result.get('expected_power', 0)
            measured = result.get('measured_power')

            measured_str = f"{measured:.2f}" if measured is not None else "-"

            row_data = [str(i), str(resistance), f"{expected:.1f}", measured_str]

            if has_current:
                current = result.get('current_ma')
                row_data.append(f"{current:.1f}" if current is not None else "-")
            if has_voltage:
                voltage = result.get('voltage_v')
                row_data.append(f"{voltage:.1f}" if voltage is not None else "-")
            if has_crest:
                cf = result.get('crest_factor')
                row_data.append(f"{cf:.2f}" if cf is not None else "-")

            data.append(row_data)

        tabla = Table(data, colWidths=col_widths, hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_SECUNDARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])

        for i in range(1, len(data)):
            if i % 2 == 0:
                style.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

        tabla.setStyle(style)
        self.elements.append(tabla)
        self.elements.append(Spacer(1, 8))

        # Agregar grafico de distribucion
        data_points = [
            (r.get('resistance', 0), r.get('measured_power', 0))
            for r in dist_results
            if r.get('measured_power') is not None
        ]
        if data_points:
            expected_power = dist_results[0].get('expected_power', 100)
            chart = self._create_distribution_chart(expected_power, data_points)
            self.elements.append(chart)
            self.elements.append(Spacer(1, 15))

    def _create_distribution_chart(self, power_level: float,
                                    data_points: List[tuple],
                                    width: int = 650, height: int = 200) -> "Drawing":
        """Crear grafico de Potencia vs Resistencia para distribucion."""
        from reportlab.graphics.shapes import Drawing, Line, String, PolyLine, Rect
        from reportlab.lib import colors

        drawing = Drawing(width, height)

        # Margenes
        margin_left = 55
        margin_right = 20
        margin_top = 25
        margin_bottom = 35

        plot_width = width - margin_left - margin_right
        plot_height = height - margin_top - margin_bottom

        # Fondo del area de grafica
        drawing.add(Rect(
            margin_left, margin_bottom,
            plot_width, plot_height,
            fillColor=colors.HexColor('#f8fafc'),
            strokeColor=colors.HexColor('#e2e8f0'),
            strokeWidth=1
        ))

        # Datos
        resistances = [p[0] for p in data_points]
        powers = [p[1] for p in data_points]

        min_r = min(resistances)
        max_r = max(resistances)
        r_range = max_r - min_r if max_r != min_r else 100

        all_powers = powers + [power_level]
        min_p = min(all_powers) * 0.85
        max_p = max(all_powers) * 1.15
        if min_p < 0:
            min_p = 0
        p_range = max_p - min_p if max_p != min_p else 10

        # Grilla horizontal
        num_grid_h = 4
        for gi in range(num_grid_h + 1):
            y = margin_bottom + (gi / num_grid_h) * plot_height
            drawing.add(Line(
                margin_left, y, margin_left + plot_width, y,
                strokeColor=colors.HexColor('#e2e8f0'),
                strokeWidth=0.3
            ))

        # Grilla vertical
        num_grid_v = min(len(resistances), 8)
        for gi in range(num_grid_v + 1):
            x = margin_left + (gi / num_grid_v) * plot_width
            drawing.add(Line(
                x, margin_bottom, x, margin_bottom + plot_height,
                strokeColor=colors.HexColor('#e2e8f0'),
                strokeWidth=0.3
            ))

        # Linea horizontal de potencia configurada (roja punteada)
        config_y = margin_bottom + ((power_level - min_p) / p_range) * plot_height
        drawing.add(Line(
            margin_left, config_y,
            margin_left + plot_width, config_y,
            strokeColor=colors.HexColor('#dc2626'),
            strokeWidth=1.0,
            strokeDashArray=[4, 3]
        ))

        # Etiqueta de linea configurada
        drawing.add(String(
            margin_left + plot_width + 2, config_y - 3,
            f"{power_level:.0f}W",
            fontSize=6,
            fillColor=colors.HexColor('#dc2626')
        ))

        # Linea de datos medidos (azul)
        points = []
        for r, p in data_points:
            x = margin_left + ((r - min_r) / r_range) * plot_width
            y = margin_bottom + ((p - min_p) / p_range) * plot_height
            points.extend([x, y])

        if len(points) >= 4:
            line = PolyLine(points, strokeColor=colors.HexColor('#2563eb'), strokeWidth=1.5)
            drawing.add(line)

        # Puntos marcados
        for r, p in data_points:
            x = margin_left + ((r - min_r) / r_range) * plot_width
            y = margin_bottom + ((p - min_p) / p_range) * plot_height
            drawing.add(Rect(
                x - 2, y - 2, 4, 4,
                fillColor=colors.HexColor('#1d4ed8'),
                strokeColor=colors.HexColor('#1d4ed8'),
                strokeWidth=0.5
            ))

        # Eje Y - Potencia (W)
        drawing.add(String(
            8, margin_bottom + plot_height / 2,
            "P (W)",
            fontSize=8,
            fillColor=colors.HexColor('#475569')
        ))

        # Valores eje Y
        for gi in range(num_grid_h + 1):
            val = min_p + (gi / num_grid_h) * p_range
            y = margin_bottom + (gi / num_grid_h) * plot_height
            drawing.add(String(
                margin_left - 5, y - 3,
                f"{val:.0f}",
                fontSize=7,
                fillColor=colors.HexColor('#64748b'),
                textAnchor='end'
            ))

        # Eje X - Resistencia
        drawing.add(String(
            margin_left + plot_width / 2, 5,
            "Impedancia (\u03A9)",
            fontSize=8,
            fillColor=colors.HexColor('#64748b'),
            textAnchor='middle'
        ))

        # Valores eje X
        num_ticks = min(len(resistances), 10)
        for gi in range(num_ticks):
            idx = int(gi * (len(resistances) - 1) / max(num_ticks - 1, 1))
            r_val = resistances[idx]
            x = margin_left + ((r_val - min_r) / r_range) * plot_width
            drawing.add(String(
                x, margin_bottom - 12,
                str(r_val),
                fontSize=7,
                fillColor=colors.HexColor('#64748b'),
                textAnchor='middle'
            ))

        # Titulo
        drawing.add(String(
            margin_left + plot_width / 2, height - 10,
            f"Distribucion de Potencia - {power_level:.0f}W",
            fontSize=9,
            fillColor=colors.HexColor('#1e293b'),
            textAnchor='middle'
        ))

        return drawing

    def _add_rf_leakage_table(self, rf_results: List[Dict]):
        """Tabla de resultados de fuga RF."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("FUGA DE CORRIENTE RF", self.style_seccion))

        data = [["#", "Electrodo", "Carga (Ω)", "Medido (mA)", "Limite (mA)", "Estado"]]

        for i, result in enumerate(rf_results, 1):
            electrode = result.get('electrode_type', '').title()
            resistance = result.get('resistance', 200)
            leakage = result.get('leakage_ma')
            max_allowed = result.get('max_allowed_ma', 150)
            status = result.get('status', '')

            leakage_str = f"{leakage:.1f}" if leakage is not None else "-"
            status_str = "✓" if status == 'pass' else "✗" if status == 'fail' else "—"

            data.append([str(i), electrode, str(resistance), leakage_str,
                        f"{max_allowed:.0f}", status_str])

        tabla = Table(data, colWidths=[35, 140, 80, 100, 100, 60], hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_SECUNDARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])

        for i, result in enumerate(rf_results, start=1):
            status = result.get('status', '')
            if status == 'pass':
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ACENTO)
            elif status == 'fail':
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))

        tabla.setStyle(style)
        self.elements.append(tabla)
        self.elements.append(Spacer(1, 15))

    def _add_rem_table(self, rem_results: List[Dict]):
        """Tabla de resultados de prueba REM/CQM.

        El analizador configura cada resistencia y el usuario observa
        a que resistencia el electrobisturi activa la alarma CQM.
        No se mide corriente ni voltaje.
        """
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("REM - MONITOREO ELECTRODO DE RETORNO", self.style_seccion))

        # Obtener resistencia de alarma CQM
        rem_alarm_resistance = None
        if rem_results:
            rem_alarm_resistance = rem_results[0].get('rem_alarm_resistance')

        data = [["#", "Resistencia (Ω)", "Tiempo (s)", "Alarma CQM"]]

        for i, result in enumerate(rem_results, 1):
            resistance = result.get('resistance', 0)
            meas_time = result.get('measurement_time_s', 5.0)

            # Alarma CQM: SI si resistance >= rem_alarm_resistance
            alarm_str = ""
            if rem_alarm_resistance is not None and resistance >= rem_alarm_resistance:
                alarm_str = "SI"

            data.append([
                str(i), str(resistance), f"{meas_time:.1f}", alarm_str
            ])

        tabla = Table(data, colWidths=[35, 160, 110, 140], hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])

        # Colorear filas con alarma CQM
        for i, result in enumerate(rem_results, start=1):
            resistance = result.get('resistance', 0)
            if rem_alarm_resistance is not None and resistance >= rem_alarm_resistance:
                style.add('BACKGROUND', (-1, i), (-1, i), colors.HexColor('#d1fae5'))
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ACENTO)
                style.add('FONTNAME', (-1, i), (-1, i), 'Helvetica-Bold')
            elif i % 2 == 0:
                style.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

        tabla.setStyle(style)
        self.elements.append(tabla)

        # Nota al pie con resistencia de alarma
        if rem_alarm_resistance is not None:
            self.elements.append(Spacer(1, 4))
            self.elements.append(Paragraph(
                f"<i>Alarma CQM activa a partir de {rem_alarm_resistance} Ω</i>",
                self.styles['Normal']
            ))
        else:
            self.elements.append(Spacer(1, 4))
            self.elements.append(Paragraph(
                "<i>Alarma CQM: no seleccionada por el usuario</i>",
                self.styles['Normal']
            ))

        self.elements.append(Spacer(1, 15))

    def _add_statistics_table(self, statistics: Dict):
        """Tabla de estadisticas de mediciones."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("ESTADISTICAS DE MEDICIONES", self.style_seccion))

        data = [["Configuracion", "N", "Promedio (W)", "Desv. Std", "Error %"]]

        for key, stats in sorted(statistics.items()):
            if isinstance(stats, dict):
                count = stats.get('count', 0)
                average = stats.get('average')
                std_dev = stats.get('std_dev')
                error_pct = stats.get('average_error_percent')

                avg_str = f"{average:.2f}" if average is not None else "-"
                std_str = f"{std_dev:.2f}" if std_dev is not None else "-"
                error_str = f"{error_pct:+.1f}%" if error_pct is not None else "-"

                data.append([key, str(count), avg_str, std_str, error_str])

        if len(data) > 1:
            tabla = Table(data, colWidths=[200, 55, 100, 90, 90], hAlign='CENTER', repeatRows=1)

            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_SECUNDARIO),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ])

            for i in range(1, len(data)):
                if i % 2 == 0:
                    style.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

            tabla.setStyle(style)
            self.elements.append(tabla)
            self.elements.append(Spacer(1, 15))


def generate_esu_report(results_data: Dict[str, Any],
                         output_path: Optional[str] = None) -> Optional[str]:
    """Funcion de conveniencia para generar reporte de electrobisturi."""
    generator = ESUReportGenerator()
    return generator.generate_report(results_data, output_path)
