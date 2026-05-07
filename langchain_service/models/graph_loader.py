"""
图加载器。

负责从数据库加载指标图、专家图和指标-科室映射。
"""

import logging
from datetime import datetime
from typing import Dict, List, Tuple

import networkx as nx

logger = logging.getLogger(__name__)


class GraphLoader:
    """从数据库加载双图结构的工具类。"""

    def __init__(self, db_engine=None):
        self.db_engine = db_engine
        self._indicator_graph = None
        self._expert_graph = None
        self._indicator_dept_mapping = None
        self._last_reload_time = None
        self.CACHE_TTL = 3600

    def load_indicator_graph(self, force_reload: bool = False) -> nx.DiGraph:
        if self._indicator_graph is not None and not force_reload:
            if self._last_reload_time is not None:
                elapsed = (datetime.now() - self._last_reload_time).total_seconds()
                if elapsed < self.CACHE_TTL:
                    return self._indicator_graph

        logger.info("Loading indicator graph from database...")

        try:
            import sqlalchemy as sa

            with self.db_engine.connect() as conn:
                query = sa.text(
                    """
                    SELECT source_indicator, target_indicator, relation_type, weight, description
                    FROM indicator_graph
                    WHERE weight > 0
                    ORDER BY weight DESC
                    """
                )
                result = conn.execute(query)
                edges = result.fetchall()

            graph = nx.DiGraph()

            try:
                from core.agent_streaming import _GRAPH_INDICATOR_ALIAS

                for indicator_code in _GRAPH_INDICATOR_ALIAS.values():
                    if indicator_code not in graph:
                        graph.add_node(indicator_code)
            except ImportError:
                logger.warning("Could not import _GRAPH_INDICATOR_ALIAS, skipping pre-population")

            for source, target, rel_type, weight, desc in edges:
                graph.add_edge(
                    source,
                    target,
                    relation_type=rel_type,
                    weight=float(weight),
                    description=desc or "",
                )

            self._indicator_graph = graph
            self._last_reload_time = datetime.now()
            return graph
        except Exception as exc:
            logger.error("Failed to load indicator graph: %s", exc, exc_info=True)
            return self._build_fallback_indicator_graph()

    def _build_fallback_indicator_graph(self) -> nx.DiGraph:
        graph = nx.DiGraph()
        fallback_edges = [
            ("Cr", "BUN", "renal_function", 0.9, "肾功能相关"),
            ("Cr", "eGFR", "renal_function", 0.95, "肾小球滤过"),
            ("GLU", "HbA1c", "glucose_metabolism", 0.9, "糖代谢相关"),
            ("WBC", "NEUT%", "infection", 0.85, "感染炎症相关"),
            ("ALT", "AST", "liver_function", 0.9, "肝功能相关"),
            ("TBIL", "DBIL", "bilirubin", 0.8, "胆红素代谢"),
            ("K", "Na", "electrolyte", 0.7, "电解质平衡"),
            ("Hb", "RBC", "hematology", 0.85, "血液系统相关"),
            ("PLT", "WBC", "hematology", 0.6, "骨髓功能相关"),
        ]
        for source, target, rel_type, weight, desc in fallback_edges:
            graph.add_edge(
                source,
                target,
                relation_type=rel_type,
                weight=weight,
                description=desc,
            )
        self._indicator_graph = graph
        self._last_reload_time = datetime.now()
        return graph

    def load_indicator_dept_mapping(self, force_reload: bool = False) -> Dict[str, List[Tuple[str, float]]]:
        if self._indicator_dept_mapping is not None and not force_reload:
            if self._last_reload_time is not None:
                elapsed = (datetime.now() - self._last_reload_time).total_seconds()
                if elapsed < self.CACHE_TTL:
                    return self._indicator_dept_mapping

        logger.info("Loading indicator-department mapping from database...")

        try:
            import sqlalchemy as sa

            with self.db_engine.connect() as conn:
                query = sa.text(
                    """
                    SELECT indicator_name, department_name, relevance_score
                    FROM indicator_department_mapping
                    WHERE relevance_score > 0
                    ORDER BY relevance_score DESC
                    """
                )
                result = conn.execute(query)
                rows = result.fetchall()

            mapping: Dict[str, List[Tuple[str, float]]] = {}
            for indicator, department, score in rows:
                mapping.setdefault(indicator, []).append((department, float(score)))

            self._indicator_dept_mapping = mapping
            self._last_reload_time = datetime.now()
            return mapping
        except Exception as exc:
            logger.error("Failed to load indicator-department mapping: %s", exc, exc_info=True)
            return self._build_fallback_mapping()

    def _build_fallback_mapping(self) -> Dict[str, List[Tuple[str, float]]]:
        mapping = {
            "Cr": [("RenalDepartment", 0.95)],
            "BUN": [("RenalDepartment", 0.9)],
            "eGFR": [("RenalDepartment", 0.95)],
            "GLU": [("EndocrinologyDepartment", 0.95)],
            "HbA1c": [("EndocrinologyDepartment", 0.9)],
            "WBC": [("HematologyDepartment", 0.7), ("InfectiousDepartment", 0.9)],
            "NEUT%": [("InfectiousDepartment", 0.95)],
            "ALT": [("InfectiousDepartment", 0.75), ("GastroenterologyDepartment", 0.9)],
            "AST": [("InfectiousDepartment", 0.75), ("GastroenterologyDepartment", 0.9)],
            "Hb": [("HematologyDepartment", 0.95)],
            "PLT": [("HematologyDepartment", 0.9)],
            "pO2": [("RespiratoryDepartment", 0.95)],
            "pCO2": [("RespiratoryDepartment", 0.9)],
        }
        self._indicator_dept_mapping = mapping
        self._last_reload_time = datetime.now()
        return mapping

    def load_expert_graph(self, force_reload: bool = False) -> nx.DiGraph:
        if self._expert_graph is not None and not force_reload:
            if self._last_reload_time is not None:
                elapsed = (datetime.now() - self._last_reload_time).total_seconds()
                if elapsed < self.CACHE_TTL:
                    return self._expert_graph

        logger.info("Loading expert graph from database...")

        try:
            import sqlalchemy as sa

            with self.db_engine.connect() as conn:
                query = sa.text(
                    """
                    SELECT source_expert, target_expert, collaboration_type, weight, notes
                    FROM expert_collaboration_graph
                    WHERE weight > 0
                    ORDER BY weight DESC
                    """
                )
                result = conn.execute(query)
                edges = result.fetchall()

            graph = nx.DiGraph()
            for source, target, collab_type, weight, notes in edges:
                graph.add_edge(
                    source,
                    target,
                    collaboration_type=collab_type,
                    weight=float(weight),
                    notes=notes or "",
                )

            self._expert_graph = graph
            self._last_reload_time = datetime.now()
            return graph
        except Exception as exc:
            logger.error("Failed to load expert graph: %s", exc, exc_info=True)
            return self._build_fallback_expert_graph()

    def _build_fallback_expert_graph(self) -> nx.DiGraph:
        graph = nx.DiGraph()
        fallback_edges = [
            ("RenalExpert", "CardiologyExpert", "comorbidity", 0.7, "肾心综合征"),
            ("RenalExpert", "EndocrinologyExpert", "comorbidity", 0.8, "糖尿病肾病"),
            ("HematologyExpert", "InfectiousExpert", "differential", 0.6, "感染与血液鉴别"),
            ("InfectiousExpert", "RespiratoryExpert", "comorbidity", 0.75, "呼吸道感染"),
            ("EndocrinologyExpert", "CardiologyExpert", "comorbidity", 0.65, "代谢综合征"),
            ("LaboratoryExpert", "RenalExpert", "validation", 0.5, "结果复核"),
            ("LaboratoryExpert", "HematologyExpert", "validation", 0.5, "结果复核"),
        ]
        for source, target, collab_type, weight, notes in fallback_edges:
            graph.add_edge(
                source,
                target,
                collaboration_type=collab_type,
                weight=weight,
                notes=notes,
            )
        self._expert_graph = graph
        self._last_reload_time = datetime.now()
        return graph
