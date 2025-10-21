from tkinter import ttk
from typing import Callable, Optional, List, Dict
from core.macro_block import MacroBlock


class MacroTreeView(ttk.Treeview):
    """Treeview를 사용한 계층적 매크로 블록 표시 위젯."""

    # 상수
    TREEVIEW_STYLE = "MacroTree.Treeview"
    FONT_FAMILY = "Segoe UI Emoji"
    FONT_SIZE = 9
    ROW_HEIGHT = 20

    def __init__(self, master, split_cb: Callable, join_cb: Callable, desc_color: str = "#1a7f37", **kwargs):
        super().__init__(master, show='tree', selectmode='extended', **kwargs)

        self._split_cb = split_cb
        self._join_cb = join_cb
        self._desc_color = desc_color

        # 블록과 TreeView 아이템 ID 간의 양방향 매핑
        self._block_to_item: Dict[str, str] = {}
        self._item_to_block: Dict[str, MacroBlock] = {}

        self._setup_styles()

    def _setup_styles(self):
        """Treeview 스타일 설정."""
        style = ttk.Style()
        try:
            style.configure(
                self.TREEVIEW_STYLE,
                font=(self.FONT_FAMILY, self.FONT_SIZE),
                rowheight=self.ROW_HEIGHT
            )
            self.configure(style=self.TREEVIEW_STYLE)
        except Exception:
            pass  # 스타일 적용 실패 시 기본 스타일 사용

        self.tag_configure("desc", foreground=self._desc_color)

    # ========== 블록 관리 메서드 ==========

    def load_blocks(self, blocks: List[MacroBlock], parent: str = ''):
        """MacroBlock 리스트를 트리뷰에 재귀적으로 로드."""
        for block in blocks:
            item_id = self._insert_block(block, parent)
            if block.macro_blocks:
                self.load_blocks(block.macro_blocks, item_id)

    def _insert_block(self, block: MacroBlock, parent: str = '') -> str:
        """단일 MacroBlock을 트리뷰에 삽입하고 매핑 저장."""
        display_text = self._get_block_display_text(block)
        item_id = ttk.Treeview.insert(self, parent, 'end', text=display_text)

        self._block_to_item[block.key] = item_id
        self._item_to_block[item_id] = block

        return item_id

    def _get_block_display_text(self, block: MacroBlock) -> str:
        """블록의 표시 텍스트 생성."""
        display_text = block.get_display_text()
        if block.description:
            display_text = self._join_cb(display_text, block.description)
        return display_text

    def clear_all(self):
        """모든 항목 및 매핑 제거."""
        for item in self.get_children():
            ttk.Treeview.delete(self, item)
        self._block_to_item.clear()
        self._item_to_block.clear()

    def delete_block(self, block: MacroBlock):
        """블록과 자식들을 트리뷰에서 삭제."""
        item_id = self.get_item_by_block(block)
        if item_id:
            self._remove_block_mappings(item_id)
            ttk.Treeview.delete(self, item_id)

    def _remove_block_mappings(self, item_id: str):
        """블록과 그 자식들의 매핑을 재귀적으로 제거."""
        if item_id in self._item_to_block:
            block = self._item_to_block[item_id]
            del self._item_to_block[item_id]
            if block.key in self._block_to_item:
                del self._block_to_item[block.key]

        for child_id in self.get_children(item_id):
            self._remove_block_mappings(child_id)

    def update_block_display(self, block: MacroBlock):
        """블록의 표시 텍스트 업데이트."""
        item_id = self.get_item_by_block(block)
        if item_id:
            display_text = self._get_block_display_text(block)
            self.item(item_id, text=display_text)

    # ========== 블록 조회 메서드 ==========

    def get_block_by_item(self, item_id: str) -> Optional[MacroBlock]:
        """아이템 ID로 MacroBlock 반환."""
        return self._item_to_block.get(item_id)

    def get_item_by_block(self, block: MacroBlock) -> Optional[str]:
        """MacroBlock으로 아이템 ID 반환."""
        return self._block_to_item.get(block.key)

    def get_parent_block(self, block: MacroBlock) -> Optional[MacroBlock]:
        """블록의 부모 블록 반환."""
        item_id = self.get_item_by_block(block)
        if item_id:
            parent_id = self.parent(item_id)
            if parent_id:
                return self._item_to_block.get(parent_id)
        return None

    def get_selected_blocks(self) -> List[MacroBlock]:
        """선택된 블록들 반환."""
        return [self._item_to_block[item_id]
                for item_id in self.selection()
                if item_id in self._item_to_block]

    def get_selected_indices(self) -> List[int]:
        """선택된 인덱스들 반환 (flat list 기준)."""
        all_items = self._get_all_items_flat()
        return [all_items.index(item_id)
                for item_id in self.selection()
                if item_id in all_items]

    def _get_all_items_flat(self, parent: str = '') -> List[str]:
        """모든 아이템을 평면 리스트로 반환 (깊이 우선 순회)."""
        items = []
        for item_id in self.get_children(parent):
            items.append(item_id)
            items.extend(self._get_all_items_flat(item_id))
        return items

    # ========== 선택 관리 메서드 ==========

    def select_block(self, block: MacroBlock):
        """특정 블록 선택 및 스크롤."""
        item_id = self.get_item_by_block(block)
        if item_id:
            ttk.Treeview.selection_set(self, item_id)
            ttk.Treeview.see(self, item_id)

    def select_blocks(self, blocks: List[MacroBlock]):
        """여러 블록 선택."""
        item_ids = [self.get_item_by_block(block)
                    for block in blocks
                    if self.get_item_by_block(block)]

        if item_ids:
            ttk.Treeview.selection_set(self, item_ids)
            ttk.Treeview.see(self, item_ids[0])

    # ========== StyledList 호환 메서드 ==========
    # 기존 StyledList와의 호환성을 위해 정수 인덱스 기반 API 제공

    def size(self) -> int:
        """전체 아이템 수 반환."""
        return len(self._get_all_items_flat())

    def nearest(self, y: int) -> int:
        """y 좌표에 가장 가까운 아이템의 인덱스 반환."""
        item_id = self.identify_row(y)
        if item_id:
            all_items = self._get_all_items_flat()
            if item_id in all_items:
                return all_items.index(item_id)
        return -1

    def get(self, idx: int) -> str:
        """인덱스로 아이템 텍스트 반환."""
        item_id = self._get_item_id_by_index(idx)
        return self.item(item_id, 'text') if item_id else ""

    def curselection(self):
        """현재 선택된 인덱스들 반환."""
        all_items = self._get_all_items_flat()
        indices = [all_items.index(item_id)
                   for item_id in self.selection()
                   if item_id in all_items]
        return tuple(sorted(indices))

    def selection_set_multiple(self, indices: List[int]):
        """여러 인덱스 선택."""
        all_items = self._get_all_items_flat()
        item_ids = [all_items[idx]
                    for idx in indices
                    if 0 <= idx < len(all_items)]

        if item_ids:
            ttk.Treeview.selection_set(self, item_ids)

    def selection_clear(self, start=None, end=None):
        """선택 클리어."""
        current_selection = self.selection()
        if current_selection:
            self.selection_remove(*current_selection)

    def activate(self, idx: int):
        """아이템 활성화."""
        item_id = self._get_item_id_by_index(idx)
        if item_id:
            self.focus(item_id)

    # ========== 메서드 오버로딩 (정수/문자열 인자 모두 지원) ==========

    def delete(self, *args):
        """아이템 삭제 - 정수 인덱스와 item_id 모두 지원."""
        if not args:
            return

        if len(args) == 1:
            self._delete_single(args[0])
        else:
            self._delete_multiple(args)

    def _delete_single(self, arg):
        """단일 아이템 삭제."""
        if isinstance(arg, int):
            item_id = self._get_item_id_by_index(arg)
        else:
            item_id = arg

        if item_id:
            self._remove_block_mappings(item_id)
            ttk.Treeview.delete(self, item_id)

    def _delete_multiple(self, args):
        """여러 아이템 삭제."""
        for item_id in args:
            if isinstance(item_id, str) and item_id in self._item_to_block:
                self._remove_block_mappings(item_id)
        ttk.Treeview.delete(self, *args)

    def insert(self, *args, **kwargs):
        """아이템 삽입 - 정수 인덱스와 Treeview 네이티브 모두 지원."""
        if self._is_index_based_insert(args):
            self._insert_by_index(args[0], args[1])
        else:
            return ttk.Treeview.insert(self, *args, **kwargs)

    def _is_index_based_insert(self, args) -> bool:
        """인덱스 기반 insert인지 확인."""
        return len(args) == 2 and isinstance(args[0], int)

    def _insert_by_index(self, idx: int, text: str):
        """인덱스 위치에 텍스트 업데이트 (실제로는 업데이트)."""
        item_id = self._get_item_id_by_index(idx)
        if item_id:
            self.item(item_id, text=text)

    def selection_set(self, *args):
        """아이템 선택 - 정수 인덱스와 item_id 모두 지원."""
        if not args:
            return

        if len(args) == 1:
            self._selection_set_single(args[0])
        else:
            ttk.Treeview.selection_set(self, *args)

    def _selection_set_single(self, arg):
        """단일 아이템 선택."""
        if isinstance(arg, int):
            item_id = self._get_item_id_by_index(arg)
            if item_id:
                ttk.Treeview.selection_set(self, item_id)
        elif isinstance(arg, (list, tuple)):
            ttk.Treeview.selection_set(self, arg)
        else:
            ttk.Treeview.selection_set(self, arg)

    def bbox(self, idx):
        """bounding box 반환 - 정수 인덱스와 item_id 모두 지원."""
        if isinstance(idx, int):
            item_id = self._get_item_id_by_index(idx)
            return ttk.Treeview.bbox(self, item_id) if item_id else None
        return ttk.Treeview.bbox(self, idx)

    def see(self, idx):
        """아이템 스크롤 - 정수 인덱스와 item_id 모두 지원."""
        if isinstance(idx, int):
            item_id = self._get_item_id_by_index(idx)
            if item_id:
                ttk.Treeview.see(self, item_id)
        else:
            ttk.Treeview.see(self, idx)

    # ========== 유틸리티 메서드 ==========

    def _get_item_id_by_index(self, idx: int) -> Optional[str]:
        """인덱스로 item_id 반환."""
        all_items = self._get_all_items_flat()
        if 0 <= idx < len(all_items):
            return all_items[idx]
        return None
