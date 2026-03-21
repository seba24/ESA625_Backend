# -*- coding: utf-8 -*-
"""
Generador de Reportes PDF para Desfibriladores
Genera reportes profesionales de pruebas de desfibriladores Impulse 6000D/7000DP

Hereda de BaseReportGenerator para mantener formato consistente con otros módulos.

Incluye:
- Primera página estandarizada (cliente, equipo, resumen, firmas)
- Tabla detallada con error, voltaje pico, corriente pico
- Gráfica de forma de onda de descarga
- Conclusiones automáticas según IEC 60601-2-4
"""

import io
import os
import datetime
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
import logging

# Importar clase base para formato estandarizado
import sys
try:
    from app.services.reports.base_report_generator import BaseReportGenerator
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from app.services.reports.base_report_generator import BaseReportGenerator

log = logging.getLogger(__name__)


class DefibrillatorReportGenerator(BaseReportGenerator):
    """
    Generador de reportes PDF para pruebas de desfibriladores.

    Hereda de BaseReportGenerator para mantener formato consistente.
    La primera página tiene el mismo formato que seguridad eléctrica.

    Genera documentos PDF profesionales con:
    - Datos del cliente y equipo (formato estándar)
    - Resultados de mediciones de energía con error
    - Parámetros adicionales (Vpico, Ipico, tipo de onda)
    - Gráficas de forma de onda (si están disponibles)
    - Conclusiones automáticas
    """

    # Configuración del módulo
    MODULE_TITLE = "PRUEBA DE DESFIBRILADOR"
    MODULE_SUBTITLE = "Analizador Impulse 6000D/7000DP"
    MODULE_STANDARD = "IEC 60601-2-4"

    def __init__(self):
        super().__init__()
        self.include_waveform = False  # Incluir gráfica de forma de onda
        self.time_scale_ms = None  # Escala temporal para formas de onda (None = completo 50ms)
        self.report_options = None  # Opciones de reporte del protocolo

    def generate_report(self,
                       results_data: Dict[str, Any],
                       output_path: Optional[str] = None,
                       include_waveform: bool = False,
                       time_scale_ms: Optional[float] = None) -> Optional[str]:
        """
        Generar reporte PDF de resultados de desfibrilador.

        Args:
            results_data: Diccionario con datos del reporte (de results_storage)
            output_path: Ruta de salida opcional. Si no se especifica, genera nombre automático.
            include_waveform: Si True, incluye gráficas de forma de onda
            time_scale_ms: Escala temporal en ms para gráficas (None = 50ms completo)

        Returns:
            Ruta del archivo generado o None si hay error
        """
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, PageBreak, Spacer
            from reportlab.lib.units import inch
        except ImportError as e:
            log.error(f"Dependencia no instalada: {e}")
            log.error("Instalar con: pip install reportlab")
            return None

        self._init_colors_and_styles()
        self.elements = []
        self.include_waveform = include_waveform
        self.time_scale_ms = time_scale_ms

        # Extraer datos (proteger contra None)
        if not results_data:
            log.error("results_data es None o vacío")
            return None
        results = results_data.get('results', {}) or {}
        client_info = results_data.get('client', {}) or {}
        equipment_info = results_data.get('equipment', {}) or {}

        # Extraer opciones de reporte del protocolo (si existen)
        protocol = results_data.get('protocol') or {}
        self.report_options = protocol.get('report_options', {}) if isinstance(protocol, dict) else None

        # Determinar si aprobó
        overall_status = results.get('overall_status', '')
        test_passed = overall_status == 'pass'

        # Obtener contadores
        passed = results.get('passed_tests', 0)
        failed = results.get('failed_tests', 0)
        skipped = results.get('skipped_tests', 0)

        # ========== PRIMERA PÁGINA: Formato estándar (igual que seguridad eléctrica) ==========

        # 1. Título del reporte (nombre empresa, protocolo, resultado)
        protocol_name = results.get('protocol_name', 'Protocolo de Prueba')
        self._add_title_section(protocol_name, test_passed)

        # 2. Datos del cliente (formato estándar)
        self._add_client_section(client_info)

        # 3. Datos del equipo bajo prueba (formato estándar)
        self._add_equipment_section(equipment_info, "DATOS DEL EQUIPO BAJO PRUEBA (DESFIBRILADOR)")

        # 4. Información de la prueba (formato estándar)
        # Info adicional específica de desfibrilador
        extra_info = []
        defib_type = results.get('defibrillator_type', '')
        if defib_type:
            extra_info.append(("Tipo de Desfibrilador:", defib_type))

        self._add_execution_info_section(
            start_time=results.get('start_time'),
            protocol_name=protocol_name,
            passed=passed,
            failed=failed,
            skipped=skipped,
            overall_status=overall_status,
            extra_info=extra_info if extra_info else None
        )

        # 5. Datos del analizador
        analyzer_info = {
            'model': results.get('device_model', 'Impulse 7000DP'),
            'serial': results.get('device_serial', 'N/A') or 'Ver panel trasero',
        }
        self._add_analyzer_section(analyzer_info, "ANALIZADOR UTILIZADO")

        # 6. Sección de firmas (formato estándar)
        self._add_signature_section()

        # Salto de página para resultados detallados
        self.elements.append(PageBreak())

        # ========== SEGUNDA PÁGINA EN ADELANTE: Resultados específicos ==========

        # 7. Tabla de resultados detallados (específica de desfibrilador)
        self._add_results_section(results)

        # 8. Agregar estadísticas si hay múltiples repeticiones
        self._add_statistics_section(results)

        # 9. Agregar gráficas de forma de onda si están disponibles y habilitadas
        if self.include_waveform:
            self._add_waveform_section(results)

        # 10. Conclusiones (usando método estándar con textos específicos)
        conclusion_pass = (
            f"<b><font color='#10b981'>✓ EQUIPO APROBADO:</font></b> "
            f"El desfibrilador ha superado todas las pruebas de energía de descarga. "
            f"Todas las mediciones ({passed}) están dentro de la tolerancia especificada "
            f"según IEC 60601-2-4 (±4J o ±15%, el que sea mayor)."
        )
        conclusion_fail = (
            f"<b><font color='#ef4444'>✗ EQUIPO NO APROBADO:</font></b> "
            f"El desfibrilador presenta {failed} mediciones fuera de tolerancia. "
            "Se requiere calibración o mantenimiento antes de su uso clínico. "
            "Las mediciones marcadas en rojo están fuera del rango permitido."
        )
        self._add_conclusion_section(passed, failed, skipped, conclusion_pass, conclusion_fail)

        # 11. Agregar fotos si están disponibles
        photos = results_data.get('photos', [])
        if photos:
            self._add_photos_section(photos)

        # Generar ruta de salida si no se especificó
        if not output_path:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            protocol_name_file = protocol_name.replace(' ', '_')
            import tempfile
            output_dir = tempfile.gettempdir()
            output_path = os.path.join(output_dir, f"Desfibrilador_{protocol_name_file}_{timestamp}.pdf")

        # Crear PDF usando método de la clase base
        buffer = io.BytesIO()
        doc = self._create_pdf_document(buffer)

        # Construir documento
        doc.build(self.elements)

        # Guardar archivo (con seguridad si está configurada)
        buffer.seek(0)
        pdf_bytes = self._add_page_numbers(buffer.getvalue())
        pdf_bytes = self._apply_pdf_security(pdf_bytes)
        pdf_bytes = self._sign_pdf(pdf_bytes)
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)

        log.info(f"Reporte PDF generado: {output_path}")
        return output_path

    # =========================================================================
    # Implementación del método abstracto _add_results_section
    # =========================================================================

    def _add_results_section(self, results: Dict):
        """
        Agregar tablas de resultados separadas por tipo de prueba.

        Tablas generadas:
        1. MEDICIONES DE ENERGÍA - Solo pruebas de energía con tiempos de pulso
        2. TIEMPO DE CARGA - Pruebas de tiempo de carga (si existen)
        3. CARDIOVERSIÓN SINCRONIZADA - Pruebas de sincronismo (si existen)
        """
        test_results = results.get('test_results') or []

        if not test_results:
            from reportlab.platypus import Paragraph
            self.elements.append(Paragraph("No hay mediciones registradas.", self.styles['Normal']))
            return

        # Separar resultados por tipo
        # El executor guarda 'energy_output' para pruebas de energía
        energy_types = ['energy', 'energy_output']
        charge_types = ['charge_time']
        sync_types = ['sync_cardioversion', 'sync']

        battery_types = ['battery']
        energy_results = [tr for tr in test_results if tr.get('test_type') in energy_types]
        charge_time_results = [tr for tr in test_results if tr.get('test_type') in charge_types]
        sync_results = [tr for tr in test_results if tr.get('test_type') in sync_types]
        battery_results = [tr for tr in test_results if tr.get('test_type') in battery_types]
        other_results = [
            tr for tr in test_results
            if tr.get('test_type') not in energy_types + charge_types + sync_types + battery_types
        ]

        # 1. Tabla de mediciones de energía
        if energy_results:
            self._add_energy_table(energy_results)

        # 2. Tabla de tiempo de carga
        if charge_time_results:
            self._add_charge_time_table(charge_time_results)

        # 3. Tabla de cardioversión sincronizada
        if sync_results:
            self._add_sync_table(sync_results)

        # 4. Tabla de prueba de batería
        if battery_results:
            self._add_battery_table(battery_results)

        # 5. Otras pruebas (marcapasos, etc.)
        if other_results:
            self._add_other_tests_table(other_results)

    def _add_energy_table(self, energy_results: List[Dict]):
        """
        Agregar tabla de mediciones de energía.

        Formato de columna Energía: "50J @ 50Ω" (sin la palabra "Energía")

        Para Monofásico: incluye T50, T10
        Para Bifásico: incluye P1PW, P2PW, IPD, Tilt (según opciones de reporte)
        """
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("MEDICIONES DE ENERGÍA", self.style_seccion))

        # Detectar si hay resultados bifásicos (tienen más datos)
        has_biphasic = any((tr.get('raw_data') or {}).get('waveform_type') == 'biphasic' or
                          (tr.get('raw_data') or {}).get('waveform_type') == 'pulsed_biphasic'
                          for tr in energy_results)

        # Detectar si hay monofásicos
        has_monophasic = any((tr.get('raw_data') or {}).get('waveform_type') == 'monophasic'
                            for tr in energy_results)

        if has_biphasic:
            # Verificar modo de tabla bifásica
            table_mode = 'compact'
            if self.report_options:
                table_mode = self.report_options.get('biphasic_table_mode', 'compact')

            if table_mode == 'split':
                # Dos tablas separadas (Fase 1 y Fase 2)
                self._add_biphasic_split_tables(energy_results)
            else:
                # Tabla compacta (una sola tabla)
                self._add_biphasic_energy_table(energy_results)
        else:
            # Tabla para monofásico
            self._add_monophasic_energy_table(energy_results)

    def _add_monophasic_energy_table(self, energy_results: List[Dict]):
        """Tabla de energía para pulsos monofásicos."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        # Obtener opciones de reporte
        opts = self.report_options or {}
        show_peak_v = opts.get('show_peak_voltage', True)
        show_peak_i = opts.get('show_peak_current', True)
        show_pw = opts.get('show_pulse_width', True)

        # Construir encabezados dinámicamente según opciones
        headers = ["Energía", "Medido", "Error", "Rango"]
        col_widths = [70, 50, 75, 60]

        if show_peak_v:
            headers.append("Vpico")
            col_widths.append(45)
        if show_peak_i:
            headers.append("Ipico")
            col_widths.append(45)
        if show_pw:
            headers.extend(["T50", "T10"])
            col_widths.extend([40, 40])

        headers.append("Estado")
        col_widths.append(35)

        data = [headers]

        for tr in energy_results:
            raw_data = (tr.get('raw_data') or {})
            nominal = tr.get('nominal_energy') or tr.get('expected_value')
            load = tr.get('load_ohms', 50)
            measured = tr.get('measured_energy') or tr.get('measured_value')
            error_j = tr.get('error_joules')
            error_pct = tr.get('error_percent')
            min_acc = tr.get('min_acceptable')
            max_acc = tr.get('max_acceptable')
            peak_v = raw_data.get('peak_voltage') or tr.get('peak_voltage')
            peak_i = raw_data.get('peak_current') or tr.get('peak_current')
            t50 = raw_data.get('pulse_width_50')
            t10 = raw_data.get('pulse_width_10')
            status = tr.get('status', '')

            # Formato compacto: "50J @ 50Ω"
            energy_str = f"{nominal}J @ {load}Ω" if nominal is not None else "N/A"
            measured_str = f"{measured:.1f}J" if measured is not None else "N/A"

            # Error con signo
            if error_j is not None and error_pct is not None:
                error_str = f"{error_j:+.1f}J ({error_pct:+.1f}%)"
            else:
                error_str = "N/A"

            # Rango aceptable
            range_str = f"{min_acc:.0f}-{max_acc:.0f}J" if min_acc is not None and max_acc is not None else "N/A"

            status_str = {'pass': '✓', 'fail': '✗', 'skipped': '—', 'error': '!'}.get(status, '?')

            # Construir fila dinámicamente
            row = [energy_str, measured_str, error_str, range_str]

            if show_peak_v:
                row.append(f"{peak_v:.0f}V" if peak_v is not None else "-")
            if show_peak_i:
                row.append(f"{peak_i:.1f}A" if peak_i is not None else "-")
            if show_pw:
                row.append(f"{t50:.1f}ms" if t50 is not None else "-")
                row.append(f"{t10:.1f}ms" if t10 is not None else "-")

            row.append(status_str)
            data.append(row)

        # Crear tabla
        tabla = Table(data, colWidths=col_widths, hAlign='CENTER', repeatRows=1)

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
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ])

        # Colorear filas según estado
        for i, tr in enumerate(energy_results, start=1):
            status = tr.get('status', '')
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

        self.elements.append(Spacer(1, 5))
        self.elements.append(Paragraph(
            "<i>T50: Ancho de pulso al 50%. T10: Ancho de pulso al 10%. "
            "Tolerancia IEC 60601-2-4: ±4J o ±15%, el mayor.</i>",
            self.style_small
        ))
        self.elements.append(Spacer(1, 10))

    def _add_biphasic_energy_table(self, energy_results: List[Dict]):
        """Tabla de energía para pulsos bifásicos (más columnas, letra más pequeña)."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        # Obtener opciones de reporte
        opts = self.report_options or {}
        show_peak_v = opts.get('show_peak_voltage', True)
        show_peak_i = opts.get('show_peak_current', True)
        show_avg_v = opts.get('show_avg_voltage', False)
        show_avg_i = opts.get('show_avg_current', False)
        show_pw = opts.get('show_pulse_width', True)
        show_ipd = opts.get('show_ipd', True)
        show_tilt = opts.get('show_tilt', True)

        # Construir encabezados dinámicamente
        headers = ["Energía", "Medido", "Error"]
        col_widths = [55, 40, 45]

        # Fase 1
        if show_peak_v:
            headers.append("P1Vpk")
            col_widths.append(35)
        if show_avg_v:
            headers.append("P1Vav")
            col_widths.append(35)
        if show_peak_i:
            headers.append("P1Ipk")
            col_widths.append(30)
        if show_avg_i:
            headers.append("P1Iav")
            col_widths.append(30)
        if show_pw:
            headers.append("P1PW")
            col_widths.append(30)

        # Fase 2
        if show_peak_v:
            headers.append("P2Vpk")
            col_widths.append(35)
        if show_avg_v:
            headers.append("P2Vav")
            col_widths.append(35)
        if show_peak_i:
            headers.append("P2Ipk")
            col_widths.append(30)
        if show_avg_i:
            headers.append("P2Iav")
            col_widths.append(30)
        if show_pw:
            headers.append("P2PW")
            col_widths.append(30)

        # IPD y Tilt
        if show_ipd:
            headers.append("IPD")
            col_widths.append(28)
        if show_tilt:
            headers.append("Tilt")
            col_widths.append(30)

        headers.append("Est")
        col_widths.append(22)

        data = [headers]

        for tr in energy_results:
            raw_data = (tr.get('raw_data') or {})
            nominal = tr.get('nominal_energy') or tr.get('expected_value')
            load = tr.get('load_ohms', 50)
            measured = tr.get('measured_energy') or tr.get('measured_value')
            error_j = tr.get('error_joules')
            error_pct = tr.get('error_percent')
            status = tr.get('status', '')

            # Datos bifásicos
            p1_vpk = raw_data.get('phase1_peak_voltage')
            p1_vav = raw_data.get('phase1_avg_voltage')
            p1_ipk = raw_data.get('phase1_peak_current')
            p1_iav = raw_data.get('phase1_avg_current')
            p1_pw = raw_data.get('phase1_pulse_width')
            p2_vpk = raw_data.get('phase2_peak_voltage')
            p2_vav = raw_data.get('phase2_avg_voltage')
            p2_ipk = raw_data.get('phase2_peak_current')
            p2_iav = raw_data.get('phase2_avg_current')
            p2_pw = raw_data.get('phase2_pulse_width')
            ipd = raw_data.get('interphase_delay')
            tilt = raw_data.get('tilt')

            # Si es monofásico mezclado, usar datos monofásicos
            if raw_data.get('waveform_type') == 'monophasic':
                p1_vpk = raw_data.get('peak_voltage')
                p1_ipk = raw_data.get('peak_current')
                p1_pw = raw_data.get('pulse_width_50')

            # Formato compacto
            energy_str = f"{nominal}J@{load}Ω" if nominal is not None else "N/A"
            measured_str = f"{measured:.1f}J" if measured is not None else "N/A"

            if error_j is not None and error_pct is not None:
                error_str = f"{error_j:+.1f}J"
            else:
                error_str = "N/A"

            status_str = {'pass': '✓', 'fail': '✗', 'skipped': '—', 'error': '!'}.get(status, '?')

            # Construir fila dinámicamente
            row = [energy_str, measured_str, error_str]

            # Fase 1
            if show_peak_v:
                row.append(f"{p1_vpk:.0f}" if p1_vpk is not None else "-")
            if show_avg_v:
                row.append(f"{p1_vav:.0f}" if p1_vav is not None else "-")
            if show_peak_i:
                row.append(f"{p1_ipk:.1f}" if p1_ipk is not None else "-")
            if show_avg_i:
                row.append(f"{p1_iav:.1f}" if p1_iav is not None else "-")
            if show_pw:
                row.append(f"{p1_pw:.1f}" if p1_pw is not None else "-")

            # Fase 2
            if show_peak_v:
                row.append(f"{p2_vpk:.0f}" if p2_vpk is not None else "-")
            if show_avg_v:
                row.append(f"{p2_vav:.0f}" if p2_vav is not None else "-")
            if show_peak_i:
                row.append(f"{p2_ipk:.1f}" if p2_ipk is not None else "-")
            if show_avg_i:
                row.append(f"{p2_iav:.1f}" if p2_iav is not None else "-")
            if show_pw:
                row.append(f"{p2_pw:.1f}" if p2_pw is not None else "-")

            # IPD y Tilt
            if show_ipd:
                row.append(f"{ipd:.1f}" if ipd is not None else "-")
            if show_tilt:
                row.append(f"{tilt:.0f}%" if tilt is not None else "-")

            row.append(status_str)
            data.append(row)

        # Calcular tamaño de fuente según número de columnas
        num_cols = len(headers)
        if num_cols <= 8:
            font_size = 7
        elif num_cols <= 12:
            font_size = 6
        else:
            font_size = 5

        # Crear tabla con columnas dinámicas
        tabla = Table(data, colWidths=col_widths, hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), font_size),  # Tamaño dinámico
            ('FONTSIZE', (0, 1), (-1, -1), font_size),  # Tamaño dinámico
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
        ])

        # Colorear filas según estado
        for i, tr in enumerate(energy_results, start=1):
            status = tr.get('status', '')
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

        self.elements.append(Spacer(1, 5))

        # Generar leyenda dinámica
        legend_parts = ["P1/P2: Fase 1/2"]
        opts = self.report_options or {}
        if opts.get('show_peak_voltage', True):
            legend_parts.append("Vpk: Voltaje pico (V)")
        if opts.get('show_avg_voltage', False):
            legend_parts.append("Vav: Voltaje promedio (V)")
        if opts.get('show_peak_current', True):
            legend_parts.append("Ipk: Corriente pico (A)")
        if opts.get('show_avg_current', False):
            legend_parts.append("Iav: Corriente promedio (A)")
        if opts.get('show_pulse_width', True):
            legend_parts.append("PW: Ancho pulso (ms)")
        if opts.get('show_ipd', True):
            legend_parts.append("IPD: Retardo interfase (ms)")
        if opts.get('show_tilt', True):
            legend_parts.append("Tilt: Inclinación")

        self.elements.append(Paragraph(
            f"<i>{'. '.join(legend_parts)}.</i>",
            self.style_small
        ))
        self.elements.append(Spacer(1, 10))

    def _add_biphasic_split_tables(self, energy_results: List[Dict]):
        """Dos tablas separadas para bifásico: una para Fase 1 y otra para Fase 2."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        # Obtener opciones de reporte
        opts = self.report_options or {}
        show_peak_v = opts.get('show_peak_voltage', True)
        show_peak_i = opts.get('show_peak_current', True)
        show_avg_v = opts.get('show_avg_voltage', False)
        show_avg_i = opts.get('show_avg_current', False)
        show_pw = opts.get('show_pulse_width', True)
        show_ipd = opts.get('show_ipd', True)
        show_tilt = opts.get('show_tilt', True)

        # ===== TABLA FASE 1 =====
        self.elements.append(Paragraph("<b>Fase 1</b>", self.styles['Normal']))

        headers1 = ["Energía", "Medido", "Error"]
        col_widths1 = [65, 50, 55]

        if show_peak_v:
            headers1.append("Vpico")
            col_widths1.append(50)
        if show_avg_v:
            headers1.append("Vprom")
            col_widths1.append(50)
        if show_peak_i:
            headers1.append("Ipico")
            col_widths1.append(45)
        if show_avg_i:
            headers1.append("Iprom")
            col_widths1.append(45)
        if show_pw:
            headers1.append("PW")
            col_widths1.append(40)

        headers1.append("Estado")
        col_widths1.append(45)

        data1 = [headers1]

        for tr in energy_results:
            raw_data = (tr.get('raw_data') or {})
            nominal = tr.get('nominal_energy') or tr.get('expected_value')
            load = tr.get('load_ohms', 50)
            measured = tr.get('measured_energy') or tr.get('measured_value')
            error_j = tr.get('error_joules')
            error_pct = tr.get('error_percent')
            status = tr.get('status', '')

            # Datos Fase 1
            p1_vpk = raw_data.get('phase1_peak_voltage')
            p1_vav = raw_data.get('phase1_avg_voltage')
            p1_ipk = raw_data.get('phase1_peak_current')
            p1_iav = raw_data.get('phase1_avg_current')
            p1_pw = raw_data.get('phase1_pulse_width')

            # Si es monofásico mezclado
            if raw_data.get('waveform_type') == 'monophasic':
                p1_vpk = raw_data.get('peak_voltage')
                p1_ipk = raw_data.get('peak_current')
                p1_pw = raw_data.get('pulse_width_50')

            energy_str = f"{nominal}J @ {load}Ω" if nominal is not None else "N/A"
            measured_str = f"{measured:.1f}J" if measured is not None else "N/A"
            error_str = f"{error_j:+.1f}J ({error_pct:+.1f}%)" if error_j is not None else "N/A"
            status_str = {'pass': '✓ APROBADO', 'fail': '✗ RECHAZADO', 'skipped': '— OMITIDO'}.get(status, '?')

            row = [energy_str, measured_str, error_str]
            if show_peak_v:
                row.append(f"{p1_vpk:.0f}V" if p1_vpk is not None else "-")
            if show_avg_v:
                row.append(f"{p1_vav:.0f}V" if p1_vav is not None else "-")
            if show_peak_i:
                row.append(f"{p1_ipk:.1f}A" if p1_ipk is not None else "-")
            if show_avg_i:
                row.append(f"{p1_iav:.1f}A" if p1_iav is not None else "-")
            if show_pw:
                row.append(f"{p1_pw:.1f}ms" if p1_pw is not None else "-")
            row.append(status_str)

            data1.append(row)

        tabla1 = Table(data1, colWidths=col_widths1, hAlign='CENTER', repeatRows=1)
        style1 = self._create_energy_table_style(len(energy_results), 8)
        for i, tr in enumerate(energy_results, start=1):
            status = tr.get('status', '')
            if status == 'pass':
                style1.add('TEXTCOLOR', (-1, i), (-1, i), self.COLOR_ACENTO)
            elif status == 'fail':
                style1.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
                style1.add('TEXTCOLOR', (0, i), (-1, i), self.COLOR_ERROR)
            elif i % 2 == 0:
                style1.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

        tabla1.setStyle(style1)
        self.elements.append(tabla1)
        self.elements.append(Spacer(1, 10))

        # ===== TABLA FASE 2 =====
        self.elements.append(Paragraph("<b>Fase 2</b>", self.styles['Normal']))

        headers2 = ["Energía"]
        col_widths2 = [65]

        if show_peak_v:
            headers2.append("Vpico")
            col_widths2.append(50)
        if show_avg_v:
            headers2.append("Vprom")
            col_widths2.append(50)
        if show_peak_i:
            headers2.append("Ipico")
            col_widths2.append(45)
        if show_avg_i:
            headers2.append("Iprom")
            col_widths2.append(45)
        if show_pw:
            headers2.append("PW")
            col_widths2.append(40)
        if show_ipd:
            headers2.append("IPD")
            col_widths2.append(40)
        if show_tilt:
            headers2.append("Tilt")
            col_widths2.append(40)

        data2 = [headers2]

        for tr in energy_results:
            raw_data = (tr.get('raw_data') or {})
            nominal = tr.get('nominal_energy') or tr.get('expected_value')
            load = tr.get('load_ohms', 50)

            # Datos Fase 2
            p2_vpk = raw_data.get('phase2_peak_voltage')
            p2_vav = raw_data.get('phase2_avg_voltage')
            p2_ipk = raw_data.get('phase2_peak_current')
            p2_iav = raw_data.get('phase2_avg_current')
            p2_pw = raw_data.get('phase2_pulse_width')
            ipd = raw_data.get('interphase_delay')
            tilt = raw_data.get('tilt')

            energy_str = f"{nominal}J @ {load}Ω" if nominal is not None else "N/A"

            row = [energy_str]
            if show_peak_v:
                row.append(f"{p2_vpk:.0f}V" if p2_vpk is not None else "-")
            if show_avg_v:
                row.append(f"{p2_vav:.0f}V" if p2_vav is not None else "-")
            if show_peak_i:
                row.append(f"{p2_ipk:.1f}A" if p2_ipk is not None else "-")
            if show_avg_i:
                row.append(f"{p2_iav:.1f}A" if p2_iav is not None else "-")
            if show_pw:
                row.append(f"{p2_pw:.1f}ms" if p2_pw is not None else "-")
            if show_ipd:
                row.append(f"{ipd:.1f}ms" if ipd is not None else "-")
            if show_tilt:
                row.append(f"{tilt:.0f}%" if tilt is not None else "-")

            data2.append(row)

        tabla2 = Table(data2, colWidths=col_widths2, hAlign='CENTER', repeatRows=1)
        style2 = self._create_energy_table_style(len(energy_results), 8)
        for i in range(1, len(data2)):
            if i % 2 == 0:
                style2.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

        tabla2.setStyle(style2)
        self.elements.append(tabla2)
        self.elements.append(Spacer(1, 10))

        # Leyenda
        legend_parts = []
        if show_peak_v:
            legend_parts.append("Vpico: Voltaje pico")
        if show_avg_v:
            legend_parts.append("Vprom: Voltaje promedio")
        if show_peak_i:
            legend_parts.append("Ipico: Corriente pico")
        if show_avg_i:
            legend_parts.append("Iprom: Corriente promedio")
        if show_pw:
            legend_parts.append("PW: Ancho de pulso")
        if show_ipd:
            legend_parts.append("IPD: Retardo interpulso")
        if show_tilt:
            legend_parts.append("Tilt: Inclinación de onda")

        if legend_parts:
            self.elements.append(Paragraph(f"<i>{'. '.join(legend_parts)}.</i>", self.style_small))
        self.elements.append(Spacer(1, 10))

    def _create_energy_table_style(self, num_rows: int, font_size: int = 8) -> "TableStyle":
        """Crear estilo base para tablas de energía."""
        from reportlab.platypus import TableStyle
        from reportlab.lib import colors

        return TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), font_size),
            ('FONTSIZE', (0, 1), (-1, -1), font_size),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])

    def _add_charge_time_table(self, charge_time_results: List[Dict]):
        """Agregar tabla de resultados de tiempo de carga."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("TIEMPO DE CARGA", self.style_seccion))

        # Encabezados: Energía | Tiempo Medido | Máximo | Estado
        data = [["Energía", "Tiempo Medido", "Máximo Permitido", "Estado"]]

        for tr in charge_time_results:
            raw_data = (tr.get('raw_data') or {})
            test_name = tr.get('test_name', '')
            measured = tr.get('measured_value')
            expected = tr.get('expected_value')
            status = tr.get('status', '')

            # Extraer energía del nombre o raw_data
            energy = raw_data.get('energy')
            if energy is None:
                # Intentar extraer del nombre "Tiempo de carga 360J @ 50Ω"
                import re
                match = re.search(r'(\d+)J', test_name)
                energy = int(match.group(1)) if match else None

            energy_str = f"{energy}J" if energy is not None else test_name
            measured_str = f"{measured:.1f}s" if measured is not None else "N/A"
            expected_str = f"{expected:.1f}s" if expected is not None else "N/A"

            status_str = {
                'pass': 'APROBADO',
                'fail': 'RECHAZADO',
                'skipped': 'OMITIDO',
                'error': 'ERROR'
            }.get(status, status.upper() if status else 'N/A')

            data.append([energy_str, measured_str, expected_str, status_str])

        tabla = Table(data, colWidths=[100, 120, 120, 100], hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])

        # Colorear según estado
        for i, tr in enumerate(charge_time_results, start=1):
            status = tr.get('status', '')
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

        self.elements.append(Spacer(1, 5))
        self.elements.append(Paragraph(
            "<i>Tiempo máximo de carga según IEC 60601-2-4: ≤15s para energía máxima.</i>",
            self.style_small
        ))
        self.elements.append(Spacer(1, 10))

    def _add_sync_table(self, sync_results: List[Dict]):
        """Agregar tabla de resultados de cardioversión sincronizada."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("CARDIOVERSIÓN SINCRONIZADA", self.style_seccion))

        # Encabezados: Prueba | Retardo Medido | Máximo | Energía | Estado
        data = [["Prueba", "Retardo Medido", "Máximo Permitido", "Energía", "Estado"]]

        for tr in sync_results:
            raw_data = (tr.get('raw_data') or {})
            test_name = tr.get('test_name', 'Cardioversión')
            measured = tr.get('measured_value')
            expected = tr.get('expected_value')
            energy = raw_data.get('energy')
            status = tr.get('status', '')

            measured_str = f"{measured:.0f}ms" if measured is not None else "N/A"
            expected_str = f"≤{expected:.0f}ms" if expected is not None else "N/A"
            energy_str = f"{energy:.1f}J" if energy is not None else "-"

            status_str = {
                'pass': 'APROBADO',
                'fail': 'RECHAZADO',
                'skipped': 'OMITIDO',
                'error': 'ERROR'
            }.get(status, status.upper() if status else 'N/A')

            data.append([test_name, measured_str, expected_str, energy_str, status_str])

        tabla = Table(data, colWidths=[120, 100, 100, 80, 80], hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])

        # Colorear según estado
        for i, tr in enumerate(sync_results, start=1):
            status = tr.get('status', '')
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

        self.elements.append(Spacer(1, 5))
        self.elements.append(Paragraph(
            "<i>Retardo de sincronización: tiempo desde pico R del ECG hasta la descarga. "
            "Máximo típico según IEC 60601-2-4: ≤60ms.</i>",
            self.style_small
        ))
        self.elements.append(Spacer(1, 10))

    def _add_battery_table(self, battery_results: List[Dict]):
        """
        Agregar tabla de prueba de capacidad de batería.

        Columnas: N° | Nominal (J) | Medido (J) | Error (J) | Error (%) | Vpk (V) | Ipk (A) | T.Carga (s) | Estado
        Fila final: resumen de descargas completadas / aprobadas / rechazadas.
        """
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("PRUEBA DE CAPACIDAD DE BATERÍA", self.style_seccion))

        headers = ["N°", "Nominal\n(J)", "Medido\n(J)", "Error\n(J)", "Error\n(%)",
                   "Vpk\n(V)", "Ipk\n(A)", "T.Carga\n(s)", "Estado"]
        col_widths = [22, 42, 42, 42, 42, 42, 42, 42, 52]

        data = [headers]

        passed_count = 0
        failed_count = 0

        for idx, tr in enumerate(battery_results, start=1):
            status = tr.get('status', '')
            nominal = tr.get('nominal_energy') or tr.get('expected_value', '')
            measured = tr.get('measured_energy') or tr.get('measured_value')
            error_j = tr.get('error_joules')
            error_pct = tr.get('error_percent')
            vpk = tr.get('peak_voltage')
            ipk = tr.get('peak_current')
            charge_t = tr.get('charge_time')

            # Calcular error si no viene precalculado
            if error_j is None and measured is not None and nominal:
                error_j = measured - float(nominal)
            if error_pct is None and measured is not None and nominal and float(nominal) != 0:
                error_pct = ((measured - float(nominal)) / float(nominal)) * 100

            def _fmt(v, decimals=1):
                return f"{v:.{decimals}f}" if v is not None else "—"

            status_str = "APROBADO" if status == 'pass' else ("RECHAZADO" if status == 'fail' else status.upper())
            error_j_str = f"{error_j:+.1f}" if error_j is not None else "—"
            error_pct_str = f"{error_pct:+.1f}%" if error_pct is not None else "—"

            data.append([
                str(idx),
                _fmt(nominal, 0) if nominal != '' else "—",
                _fmt(measured),
                error_j_str,
                error_pct_str,
                _fmt(vpk, 0),
                _fmt(ipk, 1),
                _fmt(charge_t, 1),
                status_str,
            ])

            if status == 'pass':
                passed_count += 1
            elif status == 'fail':
                failed_count += 1

        # Fila de resumen
        total = len(battery_results)
        data.append([
            "",
            f"RESUMEN: {total} descargas completadas",
            "", "", "", "", "",
            f"APROBADAS: {passed_count}",
            f"RECHAZADAS: {failed_count}",
        ])

        tabla = Table(data, colWidths=col_widths, repeatRows=1)

        style = TableStyle([
            # Encabezado
            ('BACKGROUND',  (0, 0), (-1, 0), self.COLOR_AZUL_OSCURO),
            ('TEXTCOLOR',   (0, 0), (-1, 0), colors.white),
            ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',    (0, 0), (-1, 0), 7),
            ('ALIGN',       (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN',      (0, 0), (-1, 0), 'MIDDLE'),
            ('ROWBACKGROUND', (0, 0), (-1, 0), self.COLOR_AZUL_OSCURO),
            # Cuerpo
            ('FONTSIZE',    (0, 1), (-1, -1), 7),
            ('ALIGN',       (0, 1), (-1, -1), 'CENTER'),
            ('VALIGN',      (0, 1), (-1, -1), 'MIDDLE'),
            ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUND', (0, 1), (-1, -2), [colors.white, self.COLOR_GRIS_CLARO]),
            # Fila de resumen (última fila)
            ('BACKGROUND',  (0, -1), (-1, -1), colors.HexColor('#f3f4f6')),
            ('FONTNAME',    (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('SPAN',        (1, -1), (6, -1)),
            ('ALIGN',       (1, -1), (6, -1), 'LEFT'),
        ])

        # Colorear filas de datos según PASS/FAIL
        for i, tr in enumerate(battery_results, start=1):
            st = tr.get('status', '')
            if st == 'pass':
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f0fdf4'))
                style.add('TEXTCOLOR',  (0, i), (-1, i), colors.HexColor('#166534'))
            elif st == 'fail':
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
                style.add('TEXTCOLOR',  (0, i), (-1, i), self.COLOR_ERROR)

        tabla.setStyle(style)
        self.elements.append(tabla)
        self.elements.append(Spacer(1, 5))

        # Nota al pie con parámetros de la prueba
        if battery_results:
            first = battery_results[0]
            nominal_e = first.get('nominal_energy') or first.get('expected_value', '')
            load = first.get('load_ohms', 50)
            self.elements.append(Paragraph(
                f"<i>Prueba ejecutada con desfibrilador operando a BATERÍA. "
                f"Energía nominal: {nominal_e}J | Carga: {load}Ω | "
                f"Criterio: ±15% o ±4J (IEC 60601-2-4), el mayor.</i>",
                self.style_small
            ))
        self.elements.append(Spacer(1, 10))

    def _add_other_tests_table(self, other_results: List[Dict]):
        """Agregar tablas para otras pruebas (marcapasos, etc.)."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        # Separar resultados por tipo
        pacemaker_types = ['pacemaker_pulse', 'pacemaker_sensitivity', 'pacemaker_refractory', 'pacemaker']
        pacemaker_results = [tr for tr in other_results if tr.get('test_type') in pacemaker_types]
        remaining_results = [tr for tr in other_results if tr.get('test_type') not in pacemaker_types]

        # Tabla de marcapasos
        if pacemaker_results:
            self._add_pacemaker_table(pacemaker_results)

        # Tabla genérica para otras pruebas
        if remaining_results:
            self._add_generic_tests_table(remaining_results)

    def _add_pacemaker_table(self, pacemaker_results: List[Dict]):
        """Agregar tabla de resultados de marcapasos."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("PRUEBAS DE MARCAPASOS", self.style_seccion))

        # Separar por tipo de prueba
        pulse_results = [tr for tr in pacemaker_results if tr.get('test_type') == 'pacemaker_pulse']
        sensitivity_results = [tr for tr in pacemaker_results if tr.get('test_type') == 'pacemaker_sensitivity']
        refractory_results = [tr for tr in pacemaker_results if tr.get('test_type') == 'pacemaker_refractory']

        # === Tabla de medición de pulsos ===
        if pulse_results:
            self.elements.append(Paragraph("<b>Medición de Pulsos</b>", self.styles['Normal']))

            data = [["#", "Frecuencia", "Amplitud", "Ancho", "Energía", "Estado"]]

            for i, tr in enumerate(pulse_results, 1):
                raw_data = (tr.get('raw_data') or {})
                rate = raw_data.get('rate')
                amplitude = raw_data.get('amplitude')
                width = raw_data.get('width')
                energy = raw_data.get('energy')
                status = tr.get('status', '')

                rate_str = f"{rate} PPM" if rate is not None else "-"
                amp_str = f"{amplitude:.1f} mA" if amplitude is not None else "-"
                width_str = f"{width:.2f} ms" if width is not None else "-"
                energy_str = f"{energy:.3f} mJ" if energy is not None else "-"
                status_str = {'pass': '✓', 'fail': '✗'}.get(status, '?')

                data.append([str(i), rate_str, amp_str, width_str, energy_str, status_str])

            tabla = Table(data, colWidths=[30, 80, 80, 70, 70, 40], hAlign='CENTER', repeatRows=1)
            style = self._create_pacemaker_table_style(len(pulse_results))
            tabla.setStyle(style)
            self.elements.append(tabla)
            self.elements.append(Spacer(1, 10))

        # === Tabla de sensibilidad ===
        if sensitivity_results:
            self.elements.append(Paragraph("<b>Prueba de Sensibilidad</b>", self.styles['Normal']))

            data = [["Parámetro", "Valor", "Estado"]]

            for tr in sensitivity_results:
                raw_data = (tr.get('raw_data') or {})
                test_name = tr.get('test_name', 'Sensibilidad')
                sensitivity = raw_data.get('sensitivity_mv')
                status = tr.get('status', '')

                value_str = f"{sensitivity:.2f} mV" if sensitivity is not None else "N/A"
                status_str = {'pass': 'APROBADO', 'fail': 'RECHAZADO'}.get(status, 'N/A')

                data.append([test_name, value_str, status_str])

            tabla = Table(data, colWidths=[180, 100, 100], hAlign='CENTER', repeatRows=1)
            style = self._create_pacemaker_table_style(len(sensitivity_results))
            tabla.setStyle(style)
            self.elements.append(tabla)
            self.elements.append(Spacer(1, 5))
            self.elements.append(Paragraph(
                "<i>Sensibilidad: amplitud mínima de señal ECG que inhibe el marcapasos.</i>",
                self.style_small
            ))
            self.elements.append(Spacer(1, 10))

        # === Tabla de período refractario ===
        if refractory_results:
            self.elements.append(Paragraph("<b>Período Refractario</b>", self.styles['Normal']))

            data = [["Parámetro", "Valor", "Estado"]]

            for tr in refractory_results:
                raw_data = (tr.get('raw_data') or {})
                test_name = tr.get('test_name', 'Período Refractario')
                refractory = raw_data.get('refractory_ms')
                status = tr.get('status', '')

                value_str = f"{refractory:.0f} ms" if refractory is not None else "N/A"
                status_str = {'pass': 'APROBADO', 'fail': 'RECHAZADO'}.get(status, 'N/A')

                data.append([test_name, value_str, status_str])

            tabla = Table(data, colWidths=[180, 100, 100], hAlign='CENTER', repeatRows=1)
            style = self._create_pacemaker_table_style(len(refractory_results))
            tabla.setStyle(style)
            self.elements.append(tabla)
            self.elements.append(Spacer(1, 5))
            self.elements.append(Paragraph(
                "<i>Período refractario: tiempo después de un pulso durante el cual el marcapasos "
                "no responde a señales cardíacas.</i>",
                self.style_small
            ))
            self.elements.append(Spacer(1, 10))

    def _create_pacemaker_table_style(self, num_rows: int) -> "TableStyle":
        """Crear estilo para tablas de marcapasos."""
        from reportlab.platypus import TableStyle
        from reportlab.lib import colors

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

        # Filas alternas
        for i in range(1, num_rows + 1):
            if i % 2 == 0:
                style.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

        return style

    def _add_generic_tests_table(self, other_results: List[Dict]):
        """Agregar tabla genérica para otras pruebas."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("OTRAS PRUEBAS", self.style_seccion))

        # Encabezados genéricos
        data = [["Prueba", "Valor Medido", "Valor Esperado", "Estado"]]

        for tr in other_results:
            test_name = tr.get('test_name', 'N/A')
            measured = tr.get('measured_value')
            expected = tr.get('expected_value')
            unit = tr.get('unit', '')
            status = tr.get('status', '')

            measured_str = f"{measured}{unit}" if measured is not None else "N/A"
            expected_str = f"{expected}{unit}" if expected is not None else "N/A"

            status_str = {
                'pass': 'APROBADO',
                'fail': 'RECHAZADO',
                'skipped': 'OMITIDO',
                'error': 'ERROR'
            }.get(status, status.upper() if status else 'N/A')

            data.append([test_name, measured_str, expected_str, status_str])

        tabla = Table(data, colWidths=[150, 120, 120, 90], hAlign='CENTER', repeatRows=1)

        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])

        # Colorear según estado
        for i, tr in enumerate(other_results, start=1):
            status = tr.get('status', '')
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
        self.elements.append(Spacer(1, 10))

    def _add_statistics_section(self, results: Dict):
        """Agregar sección de estadísticas por nivel de energía"""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        statistics = results.get('statistics') or {}

        # Solo mostrar si hay estadísticas con múltiples mediciones
        has_multi_rep = any(s.get('count', 0) > 1 for s in statistics.values())
        if not statistics or not has_multi_rep:
            return

        self.elements.append(Paragraph("ESTADÍSTICAS DE REPETIBILIDAD", self.style_seccion))

        # Encabezados de tabla
        data = [["Energía", "N", "Promedio", "Error Prom.", "Desv. Std.", "Mín", "Máx", "Repetibilidad"]]

        for nominal_str, stats in sorted(statistics.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
            count = stats.get('count', 0)
            if count < 2:
                continue

            nominal = int(nominal_str) if str(nominal_str).isdigit() else nominal_str
            average = stats.get('average')
            std_dev = stats.get('std_dev')
            min_val = stats.get('min_value')
            max_val = stats.get('max_value')
            repeatability = stats.get('repeatability')
            avg_error = stats.get('average_error_percent')

            # Formatear valores
            avg_str = f"{average:.2f}J" if average is not None else "-"
            error_str = f"{avg_error:+.2f}%" if avg_error is not None else "-"
            std_str = f"{std_dev:.2f}J" if std_dev is not None else "-"
            min_str = f"{min_val:.1f}J" if min_val is not None else "-"
            max_str = f"{max_val:.1f}J" if max_val is not None else "-"
            rep_str = f"{repeatability:.2f}%" if repeatability is not None else "-"

            data.append([
                f"{nominal}J",
                str(count),
                avg_str,
                error_str,
                std_str,
                min_str,
                max_str,
                rep_str
            ])

        if len(data) <= 1:
            return

        # Crear tabla
        tabla = Table(data, colWidths=[55, 30, 60, 60, 55, 50, 50, 70], hAlign='CENTER', repeatRows=1)

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

        # Colorear filas alternas y resaltar repetibilidad
        for i in range(1, len(data)):
            if i % 2 == 0:
                style.add('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO)

            # Resaltar repetibilidad según valor
            rep_str = data[i][7]
            if rep_str != "-":
                rep_val = float(rep_str.replace('%', ''))
                if rep_val < 3:
                    style.add('TEXTCOLOR', (7, i), (7, i), self.COLOR_ACENTO)
                    style.add('FONTNAME', (7, i), (7, i), 'Helvetica-Bold')
                elif rep_val > 10:
                    style.add('TEXTCOLOR', (7, i), (7, i), self.COLOR_ERROR)
                    style.add('FONTNAME', (7, i), (7, i), 'Helvetica-Bold')

        tabla.setStyle(style)
        self.elements.append(tabla)

        # Nota explicativa
        self.elements.append(Spacer(1, 5))
        self.elements.append(Paragraph(
            "<i>Repetibilidad = (Máx - Mín) / Nominal × 100%. "
            "Valores &lt;3% indican excelente repetibilidad, &gt;10% requieren verificación.</i>",
            self.style_small
        ))
        self.elements.append(Spacer(1, 15))

    def _add_waveform_section(self, results: Dict):
        """Agregar sección con gráficas de forma de onda"""
        from reportlab.platypus import Paragraph, Spacer, Image
        from reportlab.graphics.shapes import Drawing, Line, String, Rect
        from reportlab.graphics.charts.lineplots import LinePlot
        from reportlab.graphics import renderPDF
        from reportlab.lib import colors

        test_results = results.get('test_results') or []

        # Buscar resultados con datos de forma de onda
        waveform_results = [tr for tr in test_results if tr.get('waveform_data')]

        if not waveform_results:
            return

        self.elements.append(Paragraph("FORMAS DE ONDA DE DESCARGA", self.style_seccion))

        for tr in waveform_results:  # Mostrar todas las gráficas de forma de onda
            waveform_data = tr.get('waveform_data', [])
            if not waveform_data or len(waveform_data) < 10:
                continue

            test_name = tr.get('test_name', 'Descarga')
            nominal = tr.get('nominal_energy', '')
            measured = tr.get('measured_energy', '')

            # Crear título para esta gráfica
            title = f"{test_name}"
            if measured:
                title += f" - Medido: {measured:.1f}J"

            self.elements.append(Paragraph(f"<b>{title}</b>", self.styles['Normal']))

            # Crear gráfica usando ReportLab Drawing (con marcadores de pico y tiempo)
            drawing = self._create_waveform_drawing(waveform_data, width=450, height=180,
                                                     time_scale_ms=self.time_scale_ms,
                                                     test_result=tr)
            self.elements.append(drawing)
            self.elements.append(Spacer(1, 10))

    def _create_waveform_drawing(self, waveform_data: List[float], width: int = 450, height: int = 180,
                                  time_scale_ms: Optional[float] = None,
                                  test_result: Optional[Dict] = None) -> "Drawing":
        """
        Crear gráfica de forma de onda usando ReportLab Drawing.

        Args:
            waveform_data: Lista de 2500 muestras de corriente (A)
            width: Ancho del dibujo
            height: Alto del dibujo
            time_scale_ms: Ventana temporal en ms (None = mostrar todo)
            test_result: Dict con datos del test (peak_current, raw_data, etc.)

        Returns:
            Drawing con la gráfica y marcadores de pico/tiempo
        """
        from reportlab.graphics.shapes import Drawing, Line, String, PolyLine, Rect
        from reportlab.lib import colors

        drawing = Drawing(width, height)

        # Márgenes (top aumentado para etiquetas de pico)
        margin_left = 50
        margin_right = 20
        margin_top = 30
        margin_bottom = 30

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

        # Escalar datos
        # 2500 muestras, 20µs entre muestras = 50ms total
        total_samples = len(waveform_data)
        time_per_sample_ms = 0.02  # 20µs = 0.02ms

        # Aplicar ventana temporal si se especificó
        if time_scale_ms and time_scale_ms < total_samples * time_per_sample_ms:
            num_samples = min(total_samples, int(time_scale_ms / time_per_sample_ms))
            waveform_data = waveform_data[:num_samples]
        else:
            num_samples = total_samples

        # Encontrar máximo y mínimo para escalar
        max_current = max(waveform_data) if waveform_data else 1
        min_current = min(waveform_data) if waveform_data else 0

        # Asegurar que hay rango
        if max_current == min_current:
            max_current = min_current + 1

        # Añadir margen al rango
        range_current = max_current - min_current
        max_current += range_current * 0.1
        min_current -= range_current * 0.1

        # Crear puntos para la línea
        points = []
        # Reducir número de puntos para rendimiento (cada 10 muestras)
        step = max(1, num_samples // 250)

        for i in range(0, num_samples, step):
            x = margin_left + (i / num_samples) * plot_width
            y = margin_bottom + ((waveform_data[i] - min_current) / (max_current - min_current)) * plot_height
            points.extend([x, y])

        # Dibujar línea de forma de onda
        if len(points) >= 4:
            line = PolyLine(points, strokeColor=colors.HexColor('#3b82f6'), strokeWidth=1.5)
            drawing.add(line)

        # Línea de cero si está en el rango
        if min_current <= 0 <= max_current:
            zero_y = margin_bottom + ((0 - min_current) / (max_current - min_current)) * plot_height
            drawing.add(Line(
                margin_left, zero_y,
                margin_left + plot_width, zero_y,
                strokeColor=colors.HexColor('#94a3b8'),
                strokeWidth=0.5,
                strokeDashArray=[2, 2]
            ))

        # Etiquetas de ejes
        # Eje Y - Corriente
        drawing.add(String(
            10, margin_bottom + plot_height / 2,
            "I (A)",
            fontSize=8,
            fillColor=colors.HexColor('#64748b')
        ))

        # Valores del eje Y
        for i, val in enumerate([min_current, (min_current + max_current) / 2, max_current]):
            y = margin_bottom + (i / 2) * plot_height
            drawing.add(String(
                margin_left - 5, y - 3,
                f"{val:.0f}",
                fontSize=7,
                fillColor=colors.HexColor('#64748b'),
                textAnchor='end'
            ))

        # Eje X - Tiempo
        drawing.add(String(
            margin_left + plot_width / 2, 5,
            "Tiempo (ms)",
            fontSize=8,
            fillColor=colors.HexColor('#64748b'),
            textAnchor='middle'
        ))

        # Valores del eje X
        total_time_ms = num_samples * time_per_sample_ms
        for i in range(5):
            x = margin_left + (i / 4) * plot_width
            t = (i / 4) * total_time_ms
            drawing.add(String(
                x, margin_bottom - 12,
                f"{t:.0f}",
                fontSize=7,
                fillColor=colors.HexColor('#64748b'),
                textAnchor='middle'
            ))

        # Agregar marcadores de picos de amplitud y tiempos
        if test_result:
            self._add_waveform_markers(
                drawing, waveform_data, test_result,
                margin_left, margin_bottom, plot_width, plot_height,
                min_current, max_current, num_samples, time_per_sample_ms
            )

        return drawing

    def _add_waveform_markers(self, drawing, waveform_data: List[float],
                               test_result: Dict,
                               ml: float, mb: float, pw: float, ph: float,
                               min_i: float, max_i: float,
                               num_samples: int, tps_ms: float):
        """
        Agregar marcadores de picos de amplitud y tiempos a la gráfica de forma de onda.

        Dibuja:
        - Líneas horizontales punteadas en los picos de corriente (+ y -)
        - Puntos (círculos) sobre los picos
        - Etiquetas con valor de corriente pico
        - Líneas verticales punteadas en el instante del pico
        - Etiquetas con tiempo del pico
        - Flechas de ancho de pulso (si hay datos PW disponibles)
        """
        from reportlab.graphics.shapes import Line, String, Circle
        from reportlab.lib import colors

        range_i = max_i - min_i
        if range_i <= 0:
            return

        def val_to_y(val):
            return mb + ((val - min_i) / range_i) * ph

        def idx_to_x(idx):
            return ml + (idx / num_samples) * pw

        raw_data = (test_result.get('raw_data') or {})

        # --- Detectar picos desde waveform_data ---
        peak_pos_val = max(waveform_data)
        peak_pos_idx = waveform_data.index(peak_pos_val)
        peak_neg_val = min(waveform_data)
        peak_neg_idx = waveform_data.index(peak_neg_val)

        is_biphasic = peak_neg_val < 0

        # Colores
        color_peak_pos = colors.HexColor('#ef4444')   # Rojo
        color_peak_neg = colors.HexColor('#f97316')   # Naranja
        color_time = colors.HexColor('#10b981')        # Verde
        color_pw = colors.HexColor('#8b5cf6')          # Violeta

        # --- Pico positivo ---
        peak_pos_y = val_to_y(peak_pos_val)
        peak_pos_x = idx_to_x(peak_pos_idx)
        peak_pos_t_ms = peak_pos_idx * tps_ms

        # Línea horizontal punteada al nivel del pico
        drawing.add(Line(
            ml, peak_pos_y, ml + pw, peak_pos_y,
            strokeColor=color_peak_pos, strokeWidth=0.7,
            strokeDashArray=[3, 2]
        ))

        # Punto en el pico
        drawing.add(Circle(
            peak_pos_x, peak_pos_y, 2.5,
            fillColor=color_peak_pos, strokeColor=color_peak_pos, strokeWidth=0.5
        ))

        # Etiqueta de corriente pico (usar valor del analizador si disponible)
        ipk_label_val = raw_data.get('peak_current') or test_result.get('peak_current') or peak_pos_val
        ipk_label = f"Ipk = {ipk_label_val:.1f}A"
        # Posicionar etiqueta arriba a la derecha del pico
        label_x = min(peak_pos_x + 5, ml + pw - 60)
        label_y = peak_pos_y + 5
        drawing.add(String(
            label_x, label_y,
            ipk_label, fontSize=6.5, fontName='Helvetica-Bold',
            fillColor=color_peak_pos
        ))

        # Línea vertical en el instante del pico
        drawing.add(Line(
            peak_pos_x, mb, peak_pos_x, mb + ph,
            strokeColor=color_time, strokeWidth=0.5,
            strokeDashArray=[2, 2]
        ))

        # Etiqueta de tiempo del pico (cerca del cruce por cero)
        zero_y = val_to_y(0)
        drawing.add(String(
            peak_pos_x, zero_y + 4,
            f"t={peak_pos_t_ms:.1f}ms", fontSize=6, fontName='Helvetica',
            fillColor=color_time, textAnchor='middle'
        ))

        # --- Pico negativo (solo bifásico) ---
        if is_biphasic:
            peak_neg_y = val_to_y(peak_neg_val)
            peak_neg_x = idx_to_x(peak_neg_idx)
            peak_neg_t_ms = peak_neg_idx * tps_ms

            # Línea horizontal punteada al nivel del pico negativo
            drawing.add(Line(
                ml, peak_neg_y, ml + pw, peak_neg_y,
                strokeColor=color_peak_neg, strokeWidth=0.7,
                strokeDashArray=[3, 2]
            ))

            # Punto en el pico negativo
            drawing.add(Circle(
                peak_neg_x, peak_neg_y, 2.5,
                fillColor=color_peak_neg, strokeColor=color_peak_neg, strokeWidth=0.5
            ))

            # Etiqueta de corriente pico negativo
            ipk_neg_val = raw_data.get('phase2_peak_current') or abs(peak_neg_val)
            ipk_neg_label = f"Ipk2 = {ipk_neg_val:.1f}A"
            neg_label_x = min(peak_neg_x + 5, ml + pw - 65)
            neg_label_y = peak_neg_y - 10
            drawing.add(String(
                neg_label_x, neg_label_y,
                ipk_neg_label, fontSize=6.5, fontName='Helvetica-Bold',
                fillColor=color_peak_neg
            ))

            # Línea vertical del pico negativo
            drawing.add(Line(
                peak_neg_x, mb, peak_neg_x, mb + ph,
                strokeColor=color_time, strokeWidth=0.5,
                strokeDashArray=[2, 2]
            ))

            # Etiqueta de tiempo del pico negativo (cerca del cruce por cero,
            # debajo de la etiqueta del pico positivo)
            zero_y_neg = val_to_y(0)
            drawing.add(String(
                peak_neg_x, zero_y_neg - 10,
                f"t={peak_neg_t_ms:.1f}ms", fontSize=6, fontName='Helvetica',
                fillColor=color_time, textAnchor='middle'
            ))

        # --- Anchos de pulso (PW) ---
        # Helper para dibujar una flecha de ancho de pulso
        def draw_pw_arrow(start_sample_idx, pw_val_ms, label, y_frac):
            """Dibuja flecha <--PW--> desde start_sample_idx durante pw_val_ms."""
            pw_samples_count = pw_val_ms / tps_ms
            start_idx = max(0, int(start_sample_idx))
            end_idx = min(num_samples - 1, int(start_sample_idx + pw_samples_count))
            x1 = idx_to_x(start_idx)
            x2 = idx_to_x(end_idx)
            # Posicionar a una fracción del rango Y (evitar superposición con la onda)
            y_val = min_i + (max_i - min_i) * y_frac
            ay = val_to_y(y_val)

            # Líneas verticales cortas en los extremos (ticks)
            tick = 3
            drawing.add(Line(x1, ay - tick, x1, ay + tick,
                             strokeColor=color_pw, strokeWidth=0.8))
            drawing.add(Line(x2, ay - tick, x2, ay + tick,
                             strokeColor=color_pw, strokeWidth=0.8))
            # Línea horizontal
            drawing.add(Line(x1, ay, x2, ay,
                             strokeColor=color_pw, strokeWidth=1.0))
            # Flechas
            asz = 3
            drawing.add(Line(x1, ay, x1 + asz, ay + asz / 2,
                             strokeColor=color_pw, strokeWidth=0.8))
            drawing.add(Line(x1, ay, x1 + asz, ay - asz / 2,
                             strokeColor=color_pw, strokeWidth=0.8))
            drawing.add(Line(x2, ay, x2 - asz, ay + asz / 2,
                             strokeColor=color_pw, strokeWidth=0.8))
            drawing.add(Line(x2, ay, x2 - asz, ay - asz / 2,
                             strokeColor=color_pw, strokeWidth=0.8))
            # Etiqueta encima
            mid_x = (x1 + x2) / 2
            drawing.add(String(
                mid_x, ay + 5,
                label, fontSize=6, fontName='Helvetica-Bold',
                fillColor=color_pw, textAnchor='middle'
            ))

        if is_biphasic:
            pw1 = raw_data.get('phase1_pulse_width')
            pw2 = raw_data.get('phase2_pulse_width')
            # PW1 arranca en el inicio de la descarga (sample 0)
            pw1_start = 0
            if pw1:
                draw_pw_arrow(pw1_start, pw1, f"PW1={pw1:.1f}ms", 0.78)
            # PW2 arranca al finalizar PW1 + interphase delay
            ipd = raw_data.get('interphase_delay', 0) or 0
            pw2_start = ((pw1 + ipd) / tps_ms) if pw1 else peak_neg_idx
            if pw2:
                draw_pw_arrow(pw2_start, pw2, f"PW2={pw2:.1f}ms", 0.18)
        else:
            pw50 = raw_data.get('pulse_width_50')
            # PW50 (ancho al 50% pico): arranca en el cruce ascendente del 50%
            # Si no hay dato de inicio exacto, usar inicio de la descarga (sample 0)
            pw50_start = raw_data.get('pw50_start_sample', 0)
            if pw50:
                draw_pw_arrow(pw50_start, pw50, f"PW={pw50:.1f}ms", 0.78)

    def _add_photos_section(self, photos: List[Dict]):
        """Agregar sección con fotos del equipo"""
        from reportlab.platypus import Paragraph, Spacer, Image
        from reportlab.lib.units import inch
        import os

        if not photos:
            return

        # Filtrar solo fotos que existen
        valid_photos = [p for p in photos if os.path.exists(p.get('path', ''))]
        if not valid_photos:
            return

        self.elements.append(Paragraph("FOTOS DEL EQUIPO", self.style_seccion))

        for photo in valid_photos[:4]:  # Máximo 4 fotos
            photo_path = photo.get('path', '')
            description = photo.get('description', 'Sin descripción')

            try:
                # Agregar descripción
                self.elements.append(Paragraph(f"<i>{description}</i>", self.styles['Normal']))

                # Agregar imagen
                img = Image(photo_path, width=4*inch, height=3*inch)
                img.hAlign = 'CENTER'
                self.elements.append(img)
                self.elements.append(Spacer(1, 10))

            except Exception as e:
                log.warning(f"Error agregando foto al reporte: {e}")
                continue

        self.elements.append(Spacer(1, 15))


def generate_defibrillator_report(results_data: Dict[str, Any],
                                  output_path: Optional[str] = None,
                                  include_waveform: bool = False,
                                  time_scale_ms: Optional[float] = None) -> Optional[str]:
    """
    Función de conveniencia para generar reporte de desfibrilador.

    Args:
        results_data: Datos del reporte
        output_path: Ruta de salida opcional
        include_waveform: Si incluir gráficas de forma de onda
        time_scale_ms: Escala temporal en ms para gráficas (None = 50ms completo)

    Returns:
        Ruta del archivo generado o None
    """
    generator = DefibrillatorReportGenerator()
    return generator.generate_report(results_data, output_path, include_waveform, time_scale_ms)
