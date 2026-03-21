# -*- coding: utf-8 -*-
"""
Generador de Reportes PDF para ECG Performance
Genera reportes profesionales de pruebas de performance de electrocardiógrafos

Hereda de BaseReportGenerator para mantener formato consistente con otros módulos.

Incluye:
- Primera página estandarizada (cliente, equipo, resumen, firmas)
- Tabla de señales ECG ejecutadas
- Fotos ECG capturadas desde app móvil
- Conclusiones automáticas según IEC 60601-2-25
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


class ECGPerformanceReportGenerator(BaseReportGenerator):
    """
    Generador de reportes PDF para pruebas de ECG Performance.

    Hereda de BaseReportGenerator para mantener formato consistente.
    La primera página tiene el mismo formato que seguridad eléctrica.
    """

    MODULE_TITLE = "PRUEBA DE ECG PERFORMANCE"
    MODULE_SUBTITLE = "Simulador de Señales ECG"
    MODULE_STANDARD = "IEC 60601-2-25"

    def __init__(self):
        super().__init__()

    def generate_report(self,
                       results_data: Dict[str, Any],
                       output_path: Optional[str] = None) -> Optional[str]:
        """
        Generar reporte PDF de resultados de ECG Performance.

        Args:
            results_data: Diccionario con datos del reporte (de results_storage)
            output_path: Ruta de salida opcional.

        Returns:
            Ruta del archivo generado o None si hay error
        """
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import PageBreak, Spacer
        except ImportError as e:
            log.error(f"Dependencia no instalada: {e}")
            log.error("Instalar con: pip install reportlab")
            return None

        self._init_colors_and_styles()
        self.elements = []

        # Extraer datos
        results = results_data.get('results', {})
        client_info = results_data.get('client', {})
        equipment_info = results_data.get('equipment', {})
        photos = results_data.get('photos', [])

        # Extraer opciones de logo/empresa del protocolo
        protocol = results_data.get('protocol', {})
        if isinstance(protocol, dict):
            if protocol.get('company_name'):
                self.company_name = protocol['company_name']
            if protocol.get('logo_path') and os.path.exists(protocol.get('logo_path', '')):
                self.logo_path = protocol['logo_path']

        # Calcular contadores
        waveform_results = results.get('waveform_results', [])
        successful = results.get('successful_waveforms', 0)
        failed_list = results.get('failed_waveforms', [])
        failed = len(failed_list)
        skipped = sum(1 for wr in waveform_results if wr.get('status') == 'skipped')

        overall_status = results.get('overall_status', '')
        test_passed = overall_status == 'completed_successfully'

        # ========== PRIMERA PÁGINA: Formato estándar ==========

        protocol_name = results.get('protocol_name', 'Protocolo ECG')
        self._add_title_section(protocol_name, test_passed)
        self._add_client_section(client_info)
        self._add_equipment_section(equipment_info, "DATOS DEL EQUIPO BAJO PRUEBA (ECG)")

        self._add_execution_info_section(
            start_time=results.get('start_time'),
            protocol_name=protocol_name,
            passed=successful,
            failed=failed,
            skipped=skipped,
            overall_status='pass' if test_passed else 'fail',
        )

        analyzer_info = {
            'model': results.get('device_model', 'ESA620'),
            'serial': results.get('device_serial', 'N/A') or 'Ver panel trasero',
        }
        self._add_analyzer_section(analyzer_info, "ANALIZADOR UTILIZADO")

        self._add_signature_section()

        self.elements.append(PageBreak())

        # ========== SEGUNDA PÁGINA EN ADELANTE: Resultados ==========

        self._add_results_section(results)

        # Fotos ECG
        if photos:
            self._add_ecg_photos_section(photos)

        # Respuesta en frecuencia (gráfica de transferencia) — solo si el protocolo lo indica
        ecg_config = protocol.get('ecg_config', {}) if isinstance(protocol, dict) else {}
        ref_amp = ecg_config.get('amplitude', 1.0) if isinstance(ecg_config, dict) else 1.0
        if photos and ecg_config.get('include_frequency_response', False):
            self._add_frequency_response_section(photos, ref_amp)

        # Conclusiones
        total = len(waveform_results)
        conclusion_pass = (
            f"<b><font color='#10b981'>✓ EQUIPO APROBADO:</font></b> "
            f"El electrocardiógrafo ha respondido correctamente a todas las señales "
            f"de prueba ({successful}/{total}). "
            f"El equipo cumple con los requisitos de IEC 60601-2-25."
        )
        conclusion_fail = (
            f"<b><font color='#ef4444'>✗ EQUIPO NO APROBADO:</font></b> "
            f"El electrocardiógrafo presenta {failed} señales con falla de respuesta. "
            "Se requiere calibración o revisión del equipo. "
            "Las señales marcadas en rojo no fueron procesadas correctamente."
        )
        self._add_conclusion_section(successful, failed, skipped, conclusion_pass, conclusion_fail)

        # Generar ruta de salida
        if not output_path:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            protocol_name_file = protocol_name.replace(' ', '_')
            import tempfile
            output_dir = tempfile.gettempdir()
            output_path = os.path.join(output_dir, f"ECG_{protocol_name_file}_{timestamp}.pdf")

        # Crear PDF
        buffer = io.BytesIO()
        doc = self._create_pdf_document(buffer)
        doc.build(self.elements)

        buffer.seek(0)
        pdf_bytes = self._add_page_numbers(buffer.getvalue())
        pdf_bytes = self._apply_pdf_security(pdf_bytes)
        pdf_bytes = self._sign_pdf(pdf_bytes)
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)

        log.info(f"Reporte ECG PDF generado: {output_path}")
        return output_path

    # =========================================================================
    # Implementación del método abstracto _add_results_section
    # =========================================================================

    def _add_results_section(self, results: Dict):
        """Agregar tabla de resultados de señales ECG."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        waveform_results = results.get('waveform_results', [])

        if not waveform_results:
            self.elements.append(Paragraph("No hay señales registradas.", self.styles['Normal']))
            return

        self.elements.append(Paragraph("SEÑALES ECG EJECUTADAS", self.style_seccion))

        # Encabezados
        data = [["#", "Señal", "Descripción", "Amplitud", "Duración", "Estado"]]

        for i, wr in enumerate(waveform_results, 1):
            waveform = wr.get('waveform', '')
            description = wr.get('description', '')
            amplitude = wr.get('amplitude')
            duration = wr.get('duration')
            status = wr.get('status', '')

            amp_str = f"{amplitude:.1f} mV" if amplitude is not None else "-"
            dur_str = f"{duration}s" if duration is not None else "-"

            status_str = {
                'executed': '✓ OK',
                'not_supported': '— N/S',
                'error': '✗ ERROR',
                'skipped': '— OMITIDA',
            }.get(status, '?')

            data.append([str(i), waveform, description, amp_str, dur_str, status_str])

        tabla = Table(data, colWidths=[25, 70, 175, 55, 55, 70], hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (2, 1), (2, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ])

        # Colorear filas según estado
        for i, wr in enumerate(waveform_results, start=1):
            status = wr.get('status', '')
            if status == 'executed':
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ACENTO)
                style.add('FONTNAME', (-1, i), (-1, i), 'Helvetica-Bold')
            elif status in ('error', 'not_supported'):
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
                style.add('TEXTCOLOR', (0, i), (-1, i), self.COLOR_ERROR)
            elif i % 2 == 0:
                style.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

        tabla.setStyle(style)
        self.elements.append(tabla)

        self.elements.append(Spacer(1, 5))

        # Resumen
        successful = results.get('successful_waveforms', 0)
        total = len(waveform_results)
        self.elements.append(Paragraph(
            f"<i>Total de señales: {total}. "
            f"Ejecutadas correctamente: {successful}. "
            f"Norma de referencia: IEC 60601-2-25 / IEC 60601-2-27.</i>",
            self.style_small
        ))
        self.elements.append(Spacer(1, 15))

    # =========================================================================
    # Respuesta en frecuencia — Gráfica de transferencia IEC 60601-2-25
    # =========================================================================

    def _add_frequency_response_section(self, photos: List[Dict], ref_amplitude: float):
        """
        Agregar sección de respuesta en frecuencia al reporte.

        Filtra fotos con signal_code SN*, extrae ganancia medida/esperada,
        genera gráfica vectorial logarítmica + tabla + veredicto IEC.
        """
        from reportlab.platypus import Paragraph, Spacer

        from modules.ecg_performance.protocols.models import ECG_SINUSOIDAL_FREQUENCIES

        # Extraer mediciones de fotos con señales sinusoidales
        measurements = []
        for photo in photos:
            sc = photo.get('signal_code', '')
            if sc not in ECG_SINUSOIDAL_FREQUENCIES:
                continue
            meas = photo.get('measurements', {})
            amp_data = meas.get('amplitude', {})
            measured = amp_data.get('measured')
            expected = amp_data.get('expected') or ref_amplitude
            if measured is None or expected is None or expected == 0:
                continue
            measurements.append({
                'signal_code': sc,
                'frequency_hz': ECG_SINUSOIDAL_FREQUENCIES[sc],
                'measured_mv': float(measured),
                'expected_mv': float(expected),
            })

        if len(measurements) < 2:
            return

        measurements.sort(key=lambda m: m['frequency_hz'])

        self.elements.append(Paragraph(
            "RESPUESTA EN FRECUENCIA — IEC 60601-2-25", self.style_seccion
        ))

        # Gráfica vectorial
        drawing = self._create_frequency_response_drawing(measurements, ref_amplitude)
        self.elements.append(drawing)
        self.elements.append(Spacer(1, 10))

        # Tabla de datos
        self._add_frequency_response_table(measurements)
        self.elements.append(Spacer(1, 8))

        # Veredicto IEC
        all_in_band = True
        for m in measurements:
            freq = m['frequency_hz']
            gain = m['measured_mv'] / m['expected_mv']
            if 0.5 <= freq <= 150.0:
                if gain < 0.90 or gain > 1.10:
                    all_in_band = False
                    break

        if all_in_band:
            verdict = (
                "<b><font color='#10b981'>✓ RESPUESTA EN FRECUENCIA: APROBADO</font></b> — "
                "Todas las frecuencias dentro de la banda 0.5–150 Hz presentan ganancia "
                "dentro de ±10% (IEC 60601-2-25)."
            )
        else:
            verdict = (
                "<b><font color='#ef4444'>✗ RESPUESTA EN FRECUENCIA: NO APROBADO</font></b> — "
                "Una o más frecuencias dentro de la banda 0.5–150 Hz presentan ganancia "
                "fuera de ±10% (IEC 60601-2-25)."
            )
        self.elements.append(Paragraph(verdict, self.styles['Normal']))
        self.elements.append(Spacer(1, 15))

    @staticmethod
    def _catmull_rom_spline(points_xy, num_segments=12):
        """Genera puntos interpolados con spline Catmull-Rom (puro Python).

        Args:
            points_xy: lista de (x, y) ordenados por x.
            num_segments: puntos interpolados entre cada par.
        Returns:
            Lista de (x, y) suavizados.
        """
        if len(points_xy) < 2:
            return list(points_xy)
        if len(points_xy) == 2:
            return list(points_xy)
        # Duplicar extremos para que la curva pase por primer y último punto
        pts = [points_xy[0]] + list(points_xy) + [points_xy[-1]]
        result = []
        for i in range(1, len(pts) - 2):
            p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
            for t_step in range(num_segments):
                t = t_step / num_segments
                t2, t3 = t * t, t * t * t
                x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                            (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                            (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
                y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                            (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                            (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
                result.append((x, y))
        result.append(points_xy[-1])
        return result

    def _create_frequency_response_drawing(
        self, measurements: List[Dict], ref_amplitude: float,
        width: int = 480, height: int = 200
    ) -> "Drawing":
        """
        Crear gráfica vectorial de respuesta en frecuencia (eje X logarítmico).

        Incluye banda IEC ±10% (0.5–150 Hz), grid, curva cruda (gris punteada),
        curva suavizada Catmull-Rom (azul sólida), puntos y leyenda.
        """
        from reportlab.graphics.shapes import Drawing, Line, String, PolyLine, Rect, Circle
        from reportlab.lib import colors
        import math

        drawing = Drawing(width, height)

        # Márgenes
        ml, mr, mt, mb = 50, 20, 25, 35
        pw = width - ml - mr
        ph = height - mt - mb

        # Rangos
        log_min = math.log10(0.3)   # 0.3 Hz
        log_max = math.log10(300.0)  # 300 Hz

        gains = [m['measured_mv'] / m['expected_mv'] for m in measurements]
        g_min = min(min(gains), 0.80)
        g_max = max(max(gains), 1.20)
        g_range = g_max - g_min
        g_min -= g_range * 0.05
        g_max += g_range * 0.05

        def freq_to_x(f):
            return ml + (math.log10(f) - log_min) / (log_max - log_min) * pw

        def gain_to_y(g):
            return mb + (g - g_min) / (g_max - g_min) * ph

        # Fondo
        drawing.add(Rect(
            ml, mb, pw, ph,
            fillColor=colors.HexColor('#f8fafc'),
            strokeColor=colors.HexColor('#e2e8f0'),
            strokeWidth=0.5,
        ))

        # Banda IEC: ±10% entre 0.5–150 Hz
        band_x1 = freq_to_x(0.5)
        band_x2 = freq_to_x(150.0)
        band_y1 = gain_to_y(0.90)
        band_y2 = gain_to_y(1.10)
        drawing.add(Rect(
            band_x1, band_y1, band_x2 - band_x1, band_y2 - band_y1,
            fillColor=colors.HexColor('#fef3c7'),
            strokeColor=None, strokeWidth=0,
        ))

        # Líneas límite IEC (dashed)
        for g_lim in [0.90, 1.10]:
            y_lim = gain_to_y(g_lim)
            drawing.add(Line(
                band_x1, y_lim, band_x2, y_lim,
                strokeColor=colors.HexColor('#f59e0b'),
                strokeWidth=0.8,
                strokeDashArray=[3, 2],
            ))

        # Línea de referencia 1.0 (dashed red)
        y_ref = gain_to_y(1.0)
        drawing.add(Line(
            ml, y_ref, ml + pw, y_ref,
            strokeColor=colors.HexColor('#dc2626'),
            strokeWidth=0.5,
            strokeDashArray=[4, 3],
        ))

        # Grid vertical (frecuencias típicas)
        grid_freqs = [0.5, 1, 2, 5, 10, 20, 50, 100, 200]
        for f in grid_freqs:
            if f < 0.3 or f > 300:
                continue
            x = freq_to_x(f)
            drawing.add(Line(
                x, mb, x, mb + ph,
                strokeColor=colors.HexColor('#e2e8f0'),
                strokeWidth=0.3,
            ))
            label = str(int(f)) if f >= 1 else str(f)
            drawing.add(String(
                x, mb - 12, label,
                fontSize=6, fillColor=colors.HexColor('#64748b'),
                textAnchor='middle',
            ))

        # Grid horizontal
        g_step = 0.05
        g_tick = round(g_min / g_step) * g_step
        while g_tick <= g_max:
            if g_min < g_tick < g_max:
                y = gain_to_y(g_tick)
                drawing.add(Line(
                    ml, y, ml + pw, y,
                    strokeColor=colors.HexColor('#f1f5f9'),
                    strokeWidth=0.3,
                ))
                drawing.add(String(
                    ml - 4, y - 3, f"{g_tick:.2f}",
                    fontSize=6, fillColor=colors.HexColor('#64748b'),
                    textAnchor='end',
                ))
            g_tick = round(g_tick + g_step, 3)

        # Construir puntos de datos (x_pdf, y_pdf) ordenados por frecuencia
        raw_points_xy = []
        raw_flat = []
        for m in measurements:
            x = freq_to_x(m['frequency_hz'])
            y = gain_to_y(m['measured_mv'] / m['expected_mv'])
            raw_points_xy.append((x, y))
            raw_flat.extend([x, y])

        # Curva CRUDA: segmentos rectos gris punteada (datos originales)
        if len(raw_flat) >= 4:
            drawing.add(PolyLine(
                raw_flat,
                strokeColor=colors.HexColor('#94a3b8'),
                strokeWidth=0.8,
                strokeDashArray=[3, 3],
            ))

        # Curva SUAVIZADA: spline Catmull-Rom azul sólida
        if len(raw_points_xy) >= 3:
            smooth_pts = self._catmull_rom_spline(raw_points_xy, num_segments=12)
            smooth_flat = []
            for sx, sy in smooth_pts:
                smooth_flat.extend([sx, sy])
            if len(smooth_flat) >= 4:
                drawing.add(PolyLine(
                    smooth_flat,
                    strokeColor=colors.HexColor('#2563eb'),
                    strokeWidth=1.5,
                ))
        elif len(raw_flat) >= 4:
            # < 3 puntos: no se puede suavizar, dibujar línea azul directa
            drawing.add(PolyLine(
                raw_flat,
                strokeColor=colors.HexColor('#2563eb'),
                strokeWidth=1.5,
            ))

        # Puntos medidos (círculos color-coded)
        for m in measurements:
            x = freq_to_x(m['frequency_hz'])
            gain = m['measured_mv'] / m['expected_mv']
            y = gain_to_y(gain)
            freq = m['frequency_hz']
            in_band = 0.5 <= freq <= 150.0 and 0.90 <= gain <= 1.10
            fill = colors.HexColor('#93c5fd') if in_band else colors.HexColor('#fca5a5')
            stroke = colors.HexColor('#1d4ed8') if in_band else colors.HexColor('#dc2626')
            drawing.add(Circle(x, y, 3, fillColor=fill, strokeColor=stroke, strokeWidth=0.8))

        # Leyenda (esquina superior derecha)
        lx = ml + pw - 85
        ly = mb + ph - 6
        # Fondo leyenda
        drawing.add(Rect(lx - 3, ly - 3, 88, 22,
                         fillColor=colors.Color(1, 1, 1, 0.85),
                         strokeColor=colors.HexColor('#cbd5e1'),
                         strokeWidth=0.4, rx=2, ry=2))
        # Línea azul sólida = Interpolada
        drawing.add(Line(lx, ly + 12, lx + 18, ly + 12,
                         strokeColor=colors.HexColor('#2563eb'), strokeWidth=1.5))
        drawing.add(String(lx + 21, ly + 9, "Interpolada",
                           fontSize=5.5, fillColor=colors.HexColor('#334155')))
        # Línea gris punteada = Medida
        drawing.add(Line(lx, ly + 3, lx + 18, ly + 3,
                         strokeColor=colors.HexColor('#94a3b8'), strokeWidth=0.8,
                         strokeDashArray=[3, 3]))
        drawing.add(String(lx + 21, ly, "Medida",
                           fontSize=5.5, fillColor=colors.HexColor('#334155')))

        # Etiquetas de ejes
        drawing.add(String(
            ml + pw / 2, 3, "Frecuencia (Hz)",
            fontSize=7, fillColor=colors.HexColor('#475569'), textAnchor='middle',
        ))
        drawing.add(String(
            8, mb + ph / 2, "Ganancia",
            fontSize=7, fillColor=colors.HexColor('#475569'), textAnchor='middle',
        ))

        # Título
        drawing.add(String(
            ml + pw / 2, height - 10,
            "Respuesta en Frecuencia — IEC 60601-2-25 (±10%, 0.5–150 Hz)",
            fontSize=8, fillColor=colors.HexColor('#1e293b'), textAnchor='middle',
        ))

        return drawing

    def _add_frequency_response_table(self, measurements: List[Dict]):
        """Agregar tabla con datos de respuesta en frecuencia."""
        from reportlab.platypus import Table, TableStyle, Paragraph
        from reportlab.lib import colors

        data = [["Frecuencia (Hz)", "Esperado (mV)", "Medido (mV)",
                 "Ganancia", "Desviación %", "Estado"]]

        for m in measurements:
            freq = m['frequency_hz']
            expected = m['expected_mv']
            measured = m['measured_mv']
            gain = measured / expected if expected != 0 else 1.0
            deviation = (gain - 1.0) * 100
            in_iec_band = 0.5 <= freq <= 150.0
            ok = 0.90 <= gain <= 1.10 if in_iec_band else True

            freq_str = f"{freq:.1f}" if freq < 1 else f"{int(freq)}"
            status = "✓ OK" if ok else "✗ FUERA"
            if not in_iec_band:
                status = "— F/B"  # fuera de banda IEC

            data.append([
                freq_str,
                f"{expected:.2f}",
                f"{measured:.2f}",
                f"{gain:.4f}",
                f"{deviation:+.1f}%",
                status,
            ])

        tabla = Table(data, colWidths=[65, 65, 65, 55, 65, 55], hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ])

        for i, m in enumerate(measurements, start=1):
            freq = m['frequency_hz']
            gain = m['measured_mv'] / m['expected_mv']
            in_iec_band = 0.5 <= freq <= 150.0
            if in_iec_band and (gain < 0.90 or gain > 1.10):
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ERROR)
                style.add('FONTNAME', (-1, i), (-1, i), 'Helvetica-Bold')
            elif in_iec_band:
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ACENTO)
                style.add('FONTNAME', (-1, i), (-1, i), 'Helvetica-Bold')
            if i % 2 == 0 and not (in_iec_band and (gain < 0.90 or gain > 1.10)):
                style.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

        tabla.setStyle(style)
        self.elements.append(tabla)

    def _add_ecg_photos_section(self, photos: List[Dict]):
        """Agregar sección con fotos ECG capturadas.

        Si la foto tiene mediciones (cursores del editor), dibuja overlay
        con líneas de medición y agrega tabla con valores numéricos.
        """
        from reportlab.platypus import Paragraph, Spacer, Image
        from reportlab.lib.units import inch

        valid_photos = [p for p in photos if os.path.exists(p.get('path', ''))]
        if not valid_photos:
            return

        self.elements.append(Paragraph("FOTOS ECG CAPTURADAS", self.style_seccion))

        for photo in valid_photos[:8]:
            photo_path = photo.get('path', '')
            description = photo.get('description', 'Sin descripción')
            signal_code = photo.get('signal_code', '')

            try:
                title = description
                if signal_code:
                    title = f"{signal_code}: {description}"

                self.elements.append(Paragraph(f"<i>{title}</i>", self.styles['Normal']))

                meas = photo.get('measurements', {})
                has_meas = meas.get('has_measurements', False)
                cursor_pos = meas.get('cursor_positions', {})
                has_cursors = (
                    has_meas
                    and (len(cursor_pos.get('time_lines', [])) == 2
                         or len(cursor_pos.get('amplitude_lines', [])) == 2)
                )

                if has_cursors:
                    # Foto con overlay de cursores
                    self._add_photo_with_overlay(photo_path, photo)
                else:
                    # Foto simple sin anotaciones
                    img = Image(photo_path, width=4*inch, height=3*inch)
                    img.hAlign = 'CENTER'
                    self.elements.append(img)

                self.elements.append(Spacer(1, 4))

                # Tabla de mediciones debajo de la foto
                if has_meas:
                    self._add_measurement_table(photo)

                self.elements.append(Spacer(1, 10))

            except Exception as e:
                log.warning(f"Error agregando foto ECG al reporte: {e}")
                continue

        self.elements.append(Spacer(1, 15))

    def _add_photo_with_overlay(self, photo_path: str, photo: Dict):
        """Crear Drawing con imagen de fondo y cursores de medición superpuestos."""
        from reportlab.graphics.shapes import Drawing, Image as RLImage
        from reportlab.lib.units import inch

        try:
            from PIL import Image as PILImage
            pil_img = PILImage.open(photo_path)
            img_w, img_h = pil_img.size
            pil_img.close()
        except Exception:
            img_w, img_h = 1200, 900  # fallback

        pdf_w = 4 * inch   # 288 pt
        pdf_h = 3 * inch   # 216 pt

        drawing = Drawing(pdf_w, pdf_h)

        # Imagen de fondo
        bg = RLImage(0, 0, pdf_w, pdf_h, photo_path)
        drawing.add(bg)

        # Overlay de cursores
        self._draw_measurement_overlay(drawing, photo, img_w, img_h, pdf_w, pdf_h)

        drawing.hAlign = 'CENTER'
        self.elements.append(drawing)

    def _draw_measurement_overlay(self, drawing, photo: Dict,
                                   img_w: float, img_h: float,
                                   pdf_w: float, pdf_h: float):
        """Dibujar cursores de medición sobre el Drawing de la foto.

        Cursores de tiempo: 2 líneas verticales verdes con zona sombreada + flecha delta.
        Cursores de amplitud: 2 líneas horizontales rojas con zona sombreada + flecha delta.
        """
        from reportlab.graphics.shapes import Line, String, Rect, Polygon
        from reportlab.lib import colors

        meas = photo.get('measurements', {})
        cursor_pos = meas.get('cursor_positions', {})

        scale_x = pdf_w / img_w
        scale_y = pdf_h / img_h

        color_time = colors.HexColor('#00CC00')
        color_time_dark = colors.HexColor('#009900')
        color_amp = colors.HexColor('#DD0000')
        color_amp_dark = colors.HexColor('#AA0000')
        color_time_fill = colors.Color(0, 0.8, 0, 0.10)
        color_amp_fill = colors.Color(0.8, 0, 0, 0.10)
        arrow_size = 4  # tamaño de punta de flecha

        # --- Cursores de tiempo (verticales verdes) ---
        time_lines = cursor_pos.get('time_lines', [])
        if len(time_lines) == 2:
            x1 = time_lines[0] * scale_x
            x2 = time_lines[1] * scale_x
            x_min, x_max = min(x1, x2), max(x1, x2)

            # Zona sombreada
            drawing.add(Rect(x_min, 0, x_max - x_min, pdf_h,
                             fillColor=color_time_fill, strokeColor=None))

            # Líneas T1 y T2
            for x, lbl, clr in [(x1, "T1", color_time), (x2, "T2", color_time_dark)]:
                drawing.add(Line(x, 0, x, pdf_h,
                                 strokeColor=clr, strokeWidth=1.5,
                                 strokeDashArray=[6, 3]))
                # Label arriba
                drawing.add(Rect(x + 1, pdf_h - 13, 14, 11,
                                 fillColor=colors.Color(0, 0, 0, 0.6),
                                 strokeColor=None))
                drawing.add(String(x + 3, pdf_h - 11, lbl,
                                   fontSize=7, fillColor=colors.white,
                                   fontName='Helvetica-Bold'))

            # Flecha bidireccional horizontal + valor Δt
            time_val = meas.get('time', {}).get('measured')
            if time_val is not None and (x_max - x_min) > 10:
                arrow_y = pdf_h - 28
                # Línea horizontal entre cursores
                drawing.add(Line(x_min + 3, arrow_y, x_max - 3, arrow_y,
                                 strokeColor=color_time, strokeWidth=1.2))
                # Punta izquierda →
                drawing.add(Polygon(
                    [x_min + 3, arrow_y, x_min + 3 + arrow_size, arrow_y + arrow_size / 2,
                     x_min + 3 + arrow_size, arrow_y - arrow_size / 2],
                    fillColor=color_time, strokeColor=None))
                # Punta derecha ←
                drawing.add(Polygon(
                    [x_max - 3, arrow_y, x_max - 3 - arrow_size, arrow_y + arrow_size / 2,
                     x_max - 3 - arrow_size, arrow_y - arrow_size / 2],
                    fillColor=color_time, strokeColor=None))
                # Etiqueta Δt con fondo
                mid_x = (x_min + x_max) / 2
                delta_text = f"\u0394t = {time_val:.2f} ms"
                txt_w = len(delta_text) * 4.2 + 6
                drawing.add(Rect(mid_x - txt_w / 2, arrow_y - 14, txt_w, 12,
                                 fillColor=colors.Color(0, 0.4, 0, 0.85),
                                 strokeColor=None, rx=2, ry=2))
                drawing.add(String(mid_x, arrow_y - 11, delta_text,
                                   fontSize=7, fillColor=colors.white,
                                   fontName='Helvetica-Bold',
                                   textAnchor='middle'))

        # --- Cursores de amplitud (horizontales rojos) ---
        amp_lines = cursor_pos.get('amplitude_lines', [])
        if len(amp_lines) == 2:
            y1 = pdf_h - (amp_lines[0] * scale_y)
            y2 = pdf_h - (amp_lines[1] * scale_y)
            y_min, y_max = min(y1, y2), max(y1, y2)

            # Zona sombreada
            drawing.add(Rect(0, y_min, pdf_w, y_max - y_min,
                             fillColor=color_amp_fill, strokeColor=None))

            # Líneas A1 y A2
            for y, lbl, clr in [(y1, "A1", color_amp), (y2, "A2", color_amp_dark)]:
                drawing.add(Line(0, y, pdf_w, y,
                                 strokeColor=clr, strokeWidth=1.5,
                                 strokeDashArray=[6, 3]))
                # Label izquierda
                drawing.add(Rect(2, y + 1, 14, 11,
                                 fillColor=colors.Color(0, 0, 0, 0.6),
                                 strokeColor=None))
                drawing.add(String(4, y + 3, lbl,
                                   fontSize=7, fillColor=colors.white,
                                   fontName='Helvetica-Bold'))

            # Flecha bidireccional vertical + valor ΔA
            amp_val = meas.get('amplitude', {}).get('measured')
            if amp_val is not None and (y_max - y_min) > 10:
                arrow_x = pdf_w - 30
                # Línea vertical entre cursores
                drawing.add(Line(arrow_x, y_min + 3, arrow_x, y_max - 3,
                                 strokeColor=color_amp, strokeWidth=1.2))
                # Punta abajo ↓
                drawing.add(Polygon(
                    [arrow_x, y_min + 3, arrow_x - arrow_size / 2, y_min + 3 + arrow_size,
                     arrow_x + arrow_size / 2, y_min + 3 + arrow_size],
                    fillColor=color_amp, strokeColor=None))
                # Punta arriba ↑
                drawing.add(Polygon(
                    [arrow_x, y_max - 3, arrow_x - arrow_size / 2, y_max - 3 - arrow_size,
                     arrow_x + arrow_size / 2, y_max - 3 - arrow_size],
                    fillColor=color_amp, strokeColor=None))
                # Etiqueta ΔA con fondo
                mid_y = (y_min + y_max) / 2
                delta_text = f"\u0394A = {amp_val:.2f} mV"
                txt_w = len(delta_text) * 4.2 + 6
                drawing.add(Rect(arrow_x - txt_w / 2, mid_y - 14, txt_w, 12,
                                 fillColor=colors.Color(0.5, 0, 0, 0.85),
                                 strokeColor=None, rx=2, ry=2))
                drawing.add(String(arrow_x, mid_y - 11, delta_text,
                                   fontSize=7, fillColor=colors.white,
                                   fontName='Helvetica-Bold',
                                   textAnchor='middle'))

    def _add_measurement_table(self, photo: Dict):
        """Agregar tabla con valores de medición debajo de la foto."""
        from reportlab.platypus import Table, TableStyle, Spacer, Paragraph
        from reportlab.lib import colors

        meas = photo.get('measurements', {})
        if not meas.get('has_measurements', False):
            return

        rows = []
        header = ["Parámetro", "Medido", "Esperado", "Desviación", "Estado"]
        rows.append(header)

        for key, label, unit in [
            ('amplitude', 'Amplitud', 'mV'),
            ('time', 'Tiempo', 'ms'),
            ('frequency', 'Frecuencia', 'BPM'),
        ]:
            data = meas.get(key, {})
            measured = data.get('measured')
            if measured is None:
                continue

            expected = data.get('expected')
            deviation = data.get('deviation')

            meas_str = f"{measured:.2f} {unit}"
            exp_str = f"{expected:.2f} {unit}" if expected is not None else "—"
            dev_str = f"{deviation:+.1f}%" if deviation is not None else "—"

            if deviation is not None:
                status = "✓ OK" if abs(deviation) <= 10.0 else "✗ FUERA"
            else:
                status = "—"

            rows.append([label, meas_str, exp_str, dev_str, status])

        if len(rows) <= 1:
            return

        tabla = Table(rows, colWidths=[70, 70, 70, 60, 55], hAlign='CENTER',
                      repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ])

        # Colorear estado por fila
        for i in range(1, len(rows)):
            status = rows[i][-1]
            if '✓' in status:
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ACENTO)
                style.add('FONTNAME', (-1, i), (-1, i), 'Helvetica-Bold')
            elif '✗' in status:
                style.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ERROR)
                style.add('FONTNAME', (-1, i), (-1, i), 'Helvetica-Bold')
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
            elif i % 2 == 0:
                style.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

        tabla.setStyle(style)
        self.elements.append(tabla)

        # Nota al pie con parámetros ECG
        speed = meas.get('ecg_speed_mm_s')
        gain = meas.get('ecg_gain_mm_mv')
        if speed or gain:
            parts = []
            if speed:
                parts.append(f"Vel: {speed} mm/s")
            if gain:
                parts.append(f"Ganancia: {gain} mm/mV")
            note = " | ".join(parts)
            self.elements.append(Paragraph(
                f"<i><font size='6' color='#666666'>{note}</font></i>",
                self.styles['Normal']
            ))


def generate_ecg_performance_report(results_data: Dict[str, Any],
                                     output_path: Optional[str] = None) -> Optional[str]:
    """
    Función de conveniencia para generar reporte de ECG Performance.

    Args:
        results_data: Datos del reporte
        output_path: Ruta de salida opcional

    Returns:
        Ruta del archivo generado o None
    """
    generator = ECGPerformanceReportGenerator()
    return generator.generate_report(results_data, output_path)
