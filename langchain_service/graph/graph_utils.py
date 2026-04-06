"""
双图架构的数据库交互和图加载工具

功能：
  1. 从 PostgreSQL 加载指标关联图和专家协作图
  2. 构建 NetworkX 图对象
  3. 缓存图结构以提高性能
"""

import logging
from typing import Dict, List, Tuple, Set
import networkx as nx
from datetime import datetime

logger = logging.getLogger(__name__)


class GraphLoader:
    """从数据库加载双图结构的工具类"""
    
    def __init__(self, db_engine=None):
        """
        初始化加载器
        
        Args:
            db_engine: SQLAlchemy 数据库引擎
        """
        self.db_engine = db_engine
        self._indicator_graph = None
        self._expert_graph = None
        self._indicator_dept_mapping = None
        self._last_reload_time = None
        self.CACHE_TTL = 3600  # 1小时缓存
    
    def load_indicator_graph(self, force_reload=False) -> nx.DiGraph:
        """
        加载或返回缓存的指标生理关联图
        
        Returns:
            networkx.DiGraph: 有向图，边权重表示关联强度
        """
        if self._indicator_graph is not None and not force_reload:
            # 检查缓存是否还有效
            if self._last_reload_time is not None:
                elapsed = (datetime.now() - self._last_reload_time).total_seconds()
                if elapsed < self.CACHE_TTL:
                    return self._indicator_graph
        
        logger.info("Loading indicator graph from database...")
        
        try:
            from core.config import settings
            import sqlalchemy as sa
            
            # 使用 SQLAlchemy 查询
            with self.db_engine.connect() as conn:
                query = sa.text("""
                    SELECT source_indicator, target_indicator, relation_type, weight, description
                    FROM indicator_graph
                    WHERE weight > 0
                    ORDER BY weight DESC
                """)
                result = conn.execute(query)
                edges = result.fetchall()
            
            # 构建 NetworkX 图
            G = nx.DiGraph()
            for source, target, rel_type, weight, desc in edges:
                G.add_edge(
                    source,
                    target,
                    weight=weight,
                    relation_type=rel_type,
                    description=desc
                )
                # 同时添加反向边（用于无向相关性查询）
                if rel_type in ['POSITIVE_CORR', 'NEGATIVE_CORR', 'SAME_SYSTEM']:
                    G.add_edge(
                        target,
                        source,
                        weight=weight,
                        relation_type=rel_type,
                        description=desc
                    )
            
            logger.info(f"Indicator graph loaded: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
            self._indicator_graph = G
            self._last_reload_time = datetime.now()
            return G
            
        except Exception as e:
            logger.error(f"Failed to load indicator graph: {e}")
            # 返回空图作为降级方案
            if self._indicator_graph is None:
                self._indicator_graph = nx.DiGraph()
            return self._indicator_graph
    
    def load_expert_graph(self, force_reload=False) -> nx.DiGraph:
        """
        加载或返回缓存的专家协作图
        
        Returns:
            networkx.DiGraph: 有向图，边权重表示协作强度
        """
        if self._expert_graph is not None and not force_reload:
            if self._last_reload_time is not None:
                elapsed = (datetime.now() - self._last_reload_time).total_seconds()
                if elapsed < self.CACHE_TTL:
                    return self._expert_graph
        
        logger.info("Loading expert graph from database...")
        
        try:
            from core.config import settings
            import sqlalchemy as sa
            
            with self.db_engine.connect() as conn:
                query = sa.text("""
                    SELECT source_node, target_node, relation_type, weight, description
                    FROM expert_graph
                    WHERE weight > 0
                    ORDER BY weight DESC
                """)
                result = conn.execute(query)
                edges = result.fetchall()
            
            # 构建 NetworkX 图
            G = nx.DiGraph()
            for source, target, rel_type, weight, desc in edges:
                G.add_edge(
                    source,
                    target,
                    weight=weight,
                    relation_type=rel_type,
                    description=desc
                )
            
            logger.info(f"Expert graph loaded: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
            self._expert_graph = G
            self._last_reload_time = datetime.now()
            return G
            
        except Exception as e:
            logger.error(f"Failed to load expert graph: {e}")
            if self._expert_graph is None:
                self._expert_graph = nx.DiGraph()
            return self._expert_graph
    
    def load_indicator_dept_mapping(self, force_reload=False) -> Dict[str, List[Tuple[str, float]]]:
        """
        加载指标到科室的映射关系
        
        Returns:
            Dict: {指标名 -> [(科室名, 相关度分数), ...]}
        """
        if self._indicator_dept_mapping is not None and not force_reload:
            return self._indicator_dept_mapping
        
        logger.info("Loading indicator-department mapping...")
        
        try:
            from core.config import settings
            import sqlalchemy as sa
            
            with self.db_engine.connect() as conn:
                query = sa.text("""
                    SELECT indicator_name, department_name, relevance_score
                    FROM indicator_department_mapping
                    WHERE relevance_score > 0
                    ORDER BY relevance_score DESC
                """)
                result = conn.execute(query)
                mappings = result.fetchall()
            
            # 构建映射字典
            mapping = {}
            for indicator, dept, score in mappings:
                if indicator not in mapping:
                    mapping[indicator] = []
                mapping[indicator].append((dept, score))
            
            # 按相关度排序
            for indicator in mapping:
                mapping[indicator].sort(key=lambda x: x[1], reverse=True)
            
            logger.info(f"Mapping loaded: {len(mapping)} indicators mapped to departments")
            self._indicator_dept_mapping = mapping
            return mapping
            
        except Exception as e:
            logger.error(f"Failed to load indicator-department mapping: {e}")
            if self._indicator_dept_mapping is None:
                self._indicator_dept_mapping = {}
            return self._indicator_dept_mapping
    
    @staticmethod
    def get_neighborhood_nodes(graph: nx.Graph, node: str, depth: int = 2) -> Set[str]:
        """
        获取图中一个节点的邻域节点（BFS）
        
        Args:
            graph: NetworkX 图对象
            node: 起始节点
            depth: 搜索深度
        
        Returns:
            Set: 邻域节点集合（包括起始节点自身）
        """
        if node not in graph:
            return {node}
        
        neighborhood = {node}
        current_level = {node}
        
        for _ in range(depth):
            next_level = set()
            for n in current_level:
                neighbors = set(graph.neighbors(n))
                next_level.update(neighbors - neighborhood)
            if not next_level:
                break
            neighborhood.update(next_level)
            current_level = next_level
        
        return neighborhood
