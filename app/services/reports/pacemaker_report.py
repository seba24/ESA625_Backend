# -*- coding: utf-8 -*-
"""
Generador de Reportes PDF para Marcapasos
Genera reportes profesionales de pruebas de marcapasos según IEC 60601-2-31

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


class PacemakerReportGenerator(BaseReportGenerator):
    """Generador de reportes PDF para pruebas de marcapasos."""

    MODULE_TITLE = "PRUEBA DE MARCAPASOS"
    MODULE_SUBTITLE = "Analizador de Marcapasos"
    MODULE_STANDARD = "IEC 60601-2-31"

    def __init__(self):
        super().__init__()

    def generate_report(self,
                       results_data: Dict[str, Any],
                       output_path: Optional[str] = None) -> Optional[str]:
        """Generar reporte PDF de resultados de marcapasos."""
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
        test_passed = overall_status == 'completed_successfully'

        # ========== PRIMERA PÁGINA ==========
        protocol_name = results.get('protocol_name', 'Protocolo Marcapasos')
        self._add_title_section(protocol_name, test_passed)
        self._add_client_section(client_info)
        self._add_equipment_section(equipment_info, "DATOS DEL EQUIPO BAJO PRUEBA (MARCAPASOS)")

        # Info adicional: impedancia de prueba, dispositivo, norma
        extra_info = []
        if protocol:
            tc_settings = protocol.get('transcutaneous', {})
            pacer_load = tc_settings.get('pacer_load', 0)
            if pacer_load:
                extra_info.append(("Impedancia de Prueba:", f"{pacer_load} \u03A9"))
            device_name = protocol.get('device_name', '')
            if device_name:
                extra_info.append(("Equipo Evaluado:", device_name))
            standard = protocol.get('standard', '')
            if standard:
                extra_info.append(("Norma:", standard))

        self._add_execution_info_section(
            start_time=results.get('start_time'),
            protocol_name=protocol_name,
            passed=passed,
            failed=failed,
            skipped=skipped,
            overall_status='pass' if test_passed else 'fail',
            extra_info=extra_info if extra_info else None,
        )

        analyzer_info = {
            'model': results.get('analyzer', 'Impulse 7000DP'),
            'serial': results_data.get('analyzer_serial', '') or 'N/A',
        }
        self._add_analyzer_section(analyzer_info, "ANALIZADOR UTILIZADO")

        self._add_signature_section()
        self.elements.append(PageBreak())

        # ========== SEGUNDA PÁGINA ==========
        impedance_graphs = results_data.get('impedance_graphs', [])
        self._add_results_section(results, impedance_graphs)

        # Conclusiones
        conclusion_pass = (
            f"<b><font color='#10b981'>✓ EQUIPO APROBADO:</font></b> "
            f"El marcapasos ha superado todas las pruebas ({passed}/{total}). "
            f"Los parámetros medidos cumplen con IEC 60601-2-31."
        )
        conclusion_fail = (
            f"<b><font color='#ef4444'>✗ EQUIPO NO APROBADO:</font></b> "
            f"El marcapasos presenta {failed} pruebas fuera de especificación. "
            "Se requiere calibración o revisión del equipo."
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
            output_path = os.path.join(output_dir, f"Marcapasos_{protocol_name.replace(' ', '_')}_{timestamp}.pdf")

        buffer = io.BytesIO()
        doc = self._create_pdf_document(buffer)
        doc.build(self.elements)

        buffer.seek(0)
        pdf_bytes = self._add_page_numbers(buffer.getvalue())
        pdf_bytes = self._apply_pdf_security(pdf_bytes)
        pdf_bytes = self._sign_pdf(pdf_bytes)
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)

        log.info(f"Reporte de marcapasos PDF generado: {output_path}")
        return output_path

    def _add_results_section(self, results: Dict, impedance_graphs: List = None):
        """Agregar tablas de resultados de marcapasos."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        tc_results = results.get('transcutaneous_results', [])
        sub_results = results.get('subcutaneous_results', [])
        sim_results = results.get('simulation_results', [])

        # Tabla de pruebas transcutáneas
        if tc_results:
            self._add_transcutaneous_table(tc_results)

        # Tabla de evaluación subcutánea
        if sub_results:
            self._add_subcutaneous_table(sub_results)

        # Tabla de simulación ECG paced
        if sim_results:
            self._add_simulation_table(sim_results)

        # Gráficos de impedancia
        graphs = impedance_graphs or []
        if not graphs:
            # Reconstruir desde resultados de impedancia si no se pasaron directamente
            graphs = self._reconstruct_impedance_graphs(tc_results)
        if graphs:
            self._add_impedance_graphs(graphs)

        if not tc_results and not sub_results and not sim_results and not graphs:
            self.elements.append(Paragraph("No hay mediciones registradas.", self.styles['Normal']))

    def _add_transcutaneous_table(self, tc_results: List[Dict]):
        """Tabla de resultados transcutáneos."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle

        self.elements.append(Paragraph("PRUEBAS TRANSCUTÁNEAS", self.style_seccion))

        # Estilos para celdas con texto largo (auto word-wrap)
        cell_style = ParagraphStyle(
            name='CellWrap',
            fontName='Helvetica',
            fontSize=7,
            leading=8,
            alignment=1,  # CENTER
        )
        cell_style_header = ParagraphStyle(
            name='CellWrapHeader',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=9,
            alignment=1,
            textColor=colors.white,
        )

        # Detectar si hay condiciones con contenido
        has_conditions = any(tr.get('condition', '') for tr in tc_results)

        if has_conditions:
            # 8 columnas: #, Tipo, Parámetro, Condición, Esperado, Medido, Tol., Estado
            # Total ~530pt (de 540 disponibles)
            col_widths = [22, 55, 65, 148, 65, 65, 55, 55]
            headers = ["#", "Tipo", "Parámetro", "Condición", "Esperado", "Medido", "Tol.", "Estado"]
        else:
            # 7 columnas sin Condición (más espacio para las demás)
            col_widths = [25, 70, 80, 90, 90, 75, 55]
            headers = ["#", "Tipo", "Parámetro", "Esperado", "Medido", "Tolerancia", "Estado"]

        data = [[Paragraph(h, cell_style_header) for h in headers]]

        for i, tr in enumerate(tc_results, 1):
            test_type = tr.get('test_type', '')
            parameter = tr.get('parameter', '')
            expected = tr.get('expected_value', 0)
            measured = tr.get('measured_value', 0)
            tolerance = tr.get('tolerance', 0)
            passed = tr.get('passed', False)
            unit = tr.get('unit', '')
            condition = tr.get('condition', '')

            type_display = {
                'output': 'Salida',
                'rate': 'Frecuencia',
                'sensitivity': 'Sensibilidad',
                'refractory': 'Refractario',
                'capture': 'Captura',
                'dc_leak': 'DC Leak',
                'impedance': 'Impedancia',
            }.get(test_type, test_type)

            param_display = {
                'rate': 'Frecuencia',
                'amplitude': 'Amplitud (I)',
                'width': 'Ancho pulso',
                'energy': 'Energía',
                'voltage': 'Amplitud (V)',
                'current': 'Corriente',
                'sensitivity': 'Sensibilidad',
                'refractory': 'Refractario',
                'capture': 'Captura',
                'dc_leak': 'Fuga DC',
            }.get(parameter, parameter)

            expected_str = f"{expected:.1f} {unit}" if expected else "-"
            measured_str = f"{measured:.1f} {unit}" if measured else "-"
            tolerance_str = f"±{tolerance:.1f} {unit}" if tolerance else "-"
            status_str = "✓" if passed else "✗"

            # Usar Paragraph para celdas con texto largo
            param_para = Paragraph(param_display, cell_style)
            condition_para = Paragraph(condition, cell_style)

            if has_conditions:
                row = [str(i), type_display, param_para, condition_para,
                       expected_str, measured_str, tolerance_str, status_str]
            else:
                row = [str(i), type_display, param_para,
                       expected_str, measured_str, tolerance_str, status_str]

            data.append(row)

        tabla = Table(data, colWidths=col_widths, hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ])

        for i, tr in enumerate(tc_results, start=1):
            passed = tr.get('passed', False)
            if passed:
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ACENTO)
                style.add('FONTNAME', (-1, i), (-1, i), 'Helvetica-Bold')
            else:
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
                style.add('TEXTCOLOR', (0, i), (-1, i), self.COLOR_ERROR)

        tabla.setStyle(style)
        self.elements.append(tabla)
        self.elements.append(Spacer(1, 15))

    def _add_subcutaneous_table(self, sub_results: List[Dict]):
        """Tabla de evaluación subcutánea."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("EVALUACIÓN DE MARCAPASOS IMPLANTABLE", self.style_seccion))

        for eval_data in sub_results:
            data = [
                ["Parámetro", "Valor"],
                ["Tipo de Dispositivo:", eval_data.get('device_type', 'N/A')],
                ["Fabricante:", eval_data.get('manufacturer', 'N/A')],
                ["Modelo:", eval_data.get('model', 'N/A')],
                ["Número de Serie:", eval_data.get('serial_number', 'N/A')],
                ["Frecuencia Programada:", f"{eval_data.get('programmed_rate', 0)} PPM"],
                ["Salida Programada:", f"{eval_data.get('programmed_output', 0)} V"],
                ["Umbral de Sensado:", f"{eval_data.get('sensing_threshold', 0)} mV"],
            ]

            tabla = Table(data, colWidths=[180, 220], hAlign='CENTER', repeatRows=1)
            tabla.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_SECUNDARIO),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))

            self.elements.append(tabla)
            self.elements.append(Spacer(1, 15))

    def _add_simulation_table(self, sim_results: List[Dict]):
        """Tabla de simulación ECG paced."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("SIMULACIÓN ECG PACED", self.style_seccion))

        data = [["#", "Señal", "Descripción", "Duración", "Estado"]]

        for i, sr in enumerate(sim_results, 1):
            waveform = sr.get('waveform', '')
            description = sr.get('description', '')
            duration = sr.get('duration', 0)
            status = sr.get('status', '')

            dur_str = f"{duration}s" if duration else "-"
            status_str = {
                'executed': '✓ OK',
                'not_supported': '— N/S',
                'error': '✗ ERROR',
            }.get(status, '?')

            data.append([str(i), waveform, description, dur_str, status_str])

        tabla = Table(data, colWidths=[25, 50, 200, 55, 70], hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (2, 1), (2, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])

        for i, sr in enumerate(sim_results, start=1):
            status = sr.get('status', '')
            if status == 'executed':
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ACENTO)
            elif status in ('error', 'not_supported'):
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
            elif i % 2 == 0:
                style.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

        tabla.setStyle(style)
        self.elements.append(tabla)
        self.elements.append(Spacer(1, 15))

    def _reconstruct_impedance_graphs(self, tc_results: List[Dict]) -> List[Dict]:
        """Reconstruir datos de gráficos de impedancia desde resultados individuales."""
        impedance_results = [r for r in tc_results if r.get('test_type') == 'impedance']
        if not impedance_results:
            return []

        # Agrupar por corriente configurada
        by_current = {}
        for r in impedance_results:
            raw = r.get('raw_data', {})
            current_ma = raw.get('set_current_ma', r.get('expected_value', 0))
            z_ohm = raw.get('impedance_ohm', 0)
            measured = r.get('measured_value', 0)

            if current_ma not in by_current:
                by_current[current_ma] = []
            by_current[current_ma].append((z_ohm, measured))

        graphs = []
        for current_ma, points in sorted(by_current.items()):
            graphs.append({
                'current_ma': current_ma,
                'data_points': sorted(points, key=lambda p: p[0]),
            })
        return graphs

    def _add_impedance_graphs(self, graphs: List[Dict]):
        """Agregar gráficos de Corriente vs Impedancia al reporte."""
        from reportlab.platypus import Paragraph, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph(
            "PRUEBA DE IMPEDANCIA (CORRIENTE vs IMPEDANCIA)",
            self.style_seccion
        ))

        for graph_data in graphs:
            current_ma = graph_data.get('current_ma', 0)
            data_points = graph_data.get('data_points', [])

            # Filtrar puntos nulos
            valid_points = [(z, i) for z, i in data_points if i is not None and z]
            if not valid_points:
                self.elements.append(Paragraph(
                    f"I = {current_ma} mA — Sin datos válidos",
                    self.styles['Normal']
                ))
                continue

            # Título del gráfico
            self.elements.append(Paragraph(
                f"Corriente configurada: {current_ma} mA",
                self.styles['Normal']
            ))
            self.elements.append(Spacer(1, 5))

            # Crear Drawing
            drawing = self._create_impedance_drawing(current_ma, valid_points)
            self.elements.append(drawing)
            self.elements.append(Spacer(1, 10))

            # Tabla de datos
            self._add_impedance_data_table(current_ma, valid_points)
            self.elements.append(Spacer(1, 15))

    def _create_impedance_drawing(self, current_ma: float,
                                   data_points: List[tuple],
                                   width: int = 450, height: int = 180) -> "Drawing":
        """Crear gráfico de Corriente vs Impedancia usando ReportLab Drawing."""
        from reportlab.graphics.shapes import Drawing, Line, String, PolyLine, Rect
        from reportlab.lib import colors

        drawing = Drawing(width, height)

        # Márgenes
        margin_left = 55
        margin_right = 20
        margin_top = 25
        margin_bottom = 35

        plot_width = width - margin_left - margin_right
        plot_height = height - margin_top - margin_bottom

        # Fondo del área de gráfica
        drawing.add(Rect(
            margin_left, margin_bottom,
            plot_width, plot_height,
            fillColor=colors.HexColor('#f8fafc'),
            strokeColor=colors.HexColor('#e2e8f0'),
            strokeWidth=1
        ))

        # Datos
        impedances = [p[0] for p in data_points]
        currents = [p[1] for p in data_points]

        min_z = min(impedances)
        max_z = max(impedances)
        z_range = max_z - min_z if max_z != min_z else 100

        all_currents = currents + [current_ma]
        min_i = min(all_currents)
        max_i = max(all_currents)
        i_range = max_i - min_i if max_i != min_i else 1
        # Añadir margen al rango
        min_i -= i_range * 0.15
        max_i += i_range * 0.15
        if min_i < 0:
            min_i = 0
        i_range = max_i - min_i if max_i != min_i else 1

        # Grilla horizontal (corriente)
        num_grid_h = 4
        for gi in range(num_grid_h + 1):
            y = margin_bottom + (gi / num_grid_h) * plot_height
            drawing.add(Line(
                margin_left, y, margin_left + plot_width, y,
                strokeColor=colors.HexColor('#e2e8f0'),
                strokeWidth=0.3
            ))

        # Grilla vertical (impedancia)
        num_grid_v = min(len(impedances), 8)
        for gi in range(num_grid_v + 1):
            x = margin_left + (gi / num_grid_v) * plot_width
            drawing.add(Line(
                x, margin_bottom, x, margin_bottom + plot_height,
                strokeColor=colors.HexColor('#e2e8f0'),
                strokeWidth=0.3
            ))

        # Línea ideal (corriente configurada) - roja punteada
        ideal_y = margin_bottom + ((current_ma - min_i) / i_range) * plot_height
        drawing.add(Line(
            margin_left, ideal_y,
            margin_left + plot_width, ideal_y,
            strokeColor=colors.HexColor('#dc2626'),
            strokeWidth=1.0,
            strokeDashArray=[4, 3]
        ))

        # Etiqueta de línea ideal
        drawing.add(String(
            margin_left + plot_width + 2, ideal_y - 3,
            f"{current_ma}",
            fontSize=6,
            fillColor=colors.HexColor('#dc2626')
        ))

        # Línea de datos medidos - azul
        points = []
        for z, i in data_points:
            x = margin_left + ((z - min_z) / z_range) * plot_width
            y = margin_bottom + ((i - min_i) / i_range) * plot_height
            points.extend([x, y])

        if len(points) >= 4:
            line = PolyLine(points, strokeColor=colors.HexColor('#2563eb'), strokeWidth=1.5)
            drawing.add(line)

        # Puntos marcados con círculos
        for z, i in data_points:
            x = margin_left + ((z - min_z) / z_range) * plot_width
            y = margin_bottom + ((i - min_i) / i_range) * plot_height
            # Círculo como rectángulo pequeño (ReportLab shapes no tiene Circle en Drawing)
            drawing.add(Rect(
                x - 2, y - 2, 4, 4,
                fillColor=colors.HexColor('#1d4ed8'),
                strokeColor=colors.HexColor('#1d4ed8'),
                strokeWidth=0.5
            ))

        # Eje Y - Corriente (mA)
        drawing.add(String(
            8, margin_bottom + plot_height / 2,
            "I (mA)",
            fontSize=8,
            fillColor=colors.HexColor('#475569')
        ))

        # Valores del eje Y
        for gi in range(num_grid_h + 1):
            val = min_i + (gi / num_grid_h) * i_range
            y = margin_bottom + (gi / num_grid_h) * plot_height
            drawing.add(String(
                margin_left - 5, y - 3,
                f"{val:.1f}",
                fontSize=7,
                fillColor=colors.HexColor('#64748b'),
                textAnchor='end'
            ))

        # Eje X - Impedancia (Ω)
        drawing.add(String(
            margin_left + plot_width / 2, 5,
            "Impedancia (\u03A9)",
            fontSize=8,
            fillColor=colors.HexColor('#475569'),
            textAnchor='middle'
        ))

        # Valores del eje X
        num_ticks = min(len(impedances), 8)
        for gi in range(num_ticks):
            idx = int(gi * (len(impedances) - 1) / max(num_ticks - 1, 1))
            z_val = impedances[idx]
            x = margin_left + ((z_val - min_z) / z_range) * plot_width
            drawing.add(String(
                x, margin_bottom - 12,
                str(z_val),
                fontSize=7,
                fillColor=colors.HexColor('#64748b'),
                textAnchor='middle'
            ))

        # Título del gráfico
        drawing.add(String(
            margin_left + plot_width / 2, height - 10,
            f"Corriente vs Impedancia (I config = {current_ma} mA)",
            fontSize=9,
            fillColor=colors.HexColor('#1e293b'),
            textAnchor='middle'
        ))

        return drawing

    def _add_impedance_data_table(self, current_ma: float, data_points: List[tuple]):
        """Agregar tabla de datos de impedancia."""
        from reportlab.platypus import Table, TableStyle, Spacer
        from reportlab.lib import colors

        data = [["Z (\u03A9)", "I config (mA)", "I medida (mA)", "Desv. (%)", "Estado"]]

        for z_ohm, measured in data_points:
            if current_ma > 0:
                deviation = abs(measured - current_ma) / current_ma * 100
            else:
                deviation = 0
            passed = deviation <= 15.0
            status = "\u2713" if passed else "\u2717"
            data.append([
                str(z_ohm),
                f"{current_ma:.1f}",
                f"{measured:.2f}",
                f"{deviation:.1f}%",
                status,
            ])

        tabla = Table(data, colWidths=[60, 80, 80, 60, 40], hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ])

        for i, (z_ohm, measured) in enumerate(data_points, start=1):
            deviation = abs(measured - current_ma) / current_ma * 100 if current_ma > 0 else 0
            if deviation <= 15.0:
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ACENTO)
                style.add('FONTNAME', (-1, i), (-1, i), 'Helvetica-Bold')
            else:
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
                style.add('TEXTCOLOR', (0, i), (-1, i), self.COLOR_ERROR)

        tabla.setStyle(style)
        self.elements.append(tabla)


def generate_pacemaker_report(results_data: Dict[str, Any],
                               output_path: Optional[str] = None) -> Optional[str]:
    """Función de conveniencia para generar reporte de marcapasos."""
    generator = PacemakerReportGenerator()
    return generator.generate_report(results_data, output_path)
