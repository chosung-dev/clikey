from typing import Optional, Tuple, Dict, Any
import os
import pyautogui

import cv2
import numpy as np



class ImageMatcher:
    @staticmethod
    def find_image_on_screen(template_path: str, threshold: float = 0.9, search_region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Tuple[int, int]]:
        """
        화면에서 템플릿 이미지를 찾아 중앙 좌표를 반환

        Args:
            template_path: 템플릿 이미지 파일 경로
            threshold: 매칭 임계값 (0.0 ~ 1.0)
            search_region: 검색할 영역 (x1, y1, x2, y2), None이면 전체 화면

        Returns:
            매칭된 이미지의 중앙 좌표 (x, y), 찾지 못한 경우 None
        """
        try:
            if not os.path.exists(template_path):
                return None

            # OpenCV는 한글 경로를 처리하지 못하므로 numpy를 통해 우회
            try:
                # 한글 경로 처리를 위한 우회 방법
                with open(template_path, 'rb') as f:
                    file_bytes = f.read()

                # numpy array로 변환 후 OpenCV로 디코딩
                nparr = np.frombuffer(file_bytes, np.uint8)
                template = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if template is None:
                    return None

            except Exception:
                template = cv2.imread(template_path, cv2.IMREAD_COLOR)
                if template is None:
                    return None

            # 스크린샷 캡처
            screenshot = pyautogui.screenshot()
            screenshot_np = np.array(screenshot)
            screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

            # 검색 영역이 지정된 경우 해당 영역만 크롭
            offset_x, offset_y = 0, 0
            if search_region:
                x1, y1, x2, y2 = search_region
                # 영역 유효성 검사
                screen_h, screen_w = screenshot_bgr.shape[:2]
                x1 = max(0, min(x1, screen_w - 1))
                y1 = max(0, min(y1, screen_h - 1))
                x2 = max(x1 + 1, min(x2, screen_w))
                y2 = max(y1 + 1, min(y2, screen_h))

                screenshot_bgr = screenshot_bgr[y1:y2, x1:x2]
                offset_x, offset_y = x1, y1

            result = cv2.matchTemplate(screenshot_bgr, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                template_h, template_w = template.shape[:2]
                # 오프셋을 더해 전체 화면 기준 좌표로 변환
                center_x = max_loc[0] + template_w // 2 + offset_x
                center_y = max_loc[1] + template_h // 2 + offset_y
                return (center_x, center_y)

            return None

        except Exception:
            return None

    @staticmethod
    def create_context_data(template_path: str, center_pos: Tuple[int, int]) -> Dict[str, Any]:
        """
        이미지 매칭 결과를 컨텍스트 데이터로 생성

        Args:
            template_path: 템플릿 이미지 경로
            center_pos: 매칭된 이미지의 중앙 좌표

        Returns:
            컨텍스트 데이터 딕셔너리
        """
        filename = os.path.basename(template_path)
        name_without_ext = os.path.splitext(filename)[0]

        return {
            "name": name_without_ext,
            "x": center_pos[0],
            "y": center_pos[1],
            "template_path": template_path
        }