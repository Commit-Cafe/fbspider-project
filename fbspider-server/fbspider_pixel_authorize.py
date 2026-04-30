import os
import time
import requests
from typing import Dict, Any, Optional, List


class FbspiderPixelAuthorize:

    def __init__(self, api_key: str, base_url: str = "http://47.129.247.139:7150"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
        }

    def authorize(
        self,
        pixel_id: str,
        target_account_id: str,
        username: Optional[str] = None,
        device: Optional[str] = None,
        timeout: int = 60
    ) -> Dict[str, Any]:
        task_id = self._start_authorization(
            pixel_id, target_account_id, username, device
        )

        if not task_id:
            return {
                "success": False,
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
                "authorized": False,
                "message": "发起授权任务失败"
            }

        result = self._poll_result(task_id, timeout)

        return self._format_result(pixel_id, target_account_id, result)

    def batch_authorize(
        self,
        tasks: List[Dict[str, str]],
        username: Optional[str] = None,
        device: Optional[str] = None,
        interval: int = 2,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """批量像素授权

        Args:
            tasks: 列表，每项 {"pixel_id": "xxx", "target_account_id": "yyy"}
            username: 指定用户名路由
            device: 指定设备 ID 前缀
            interval: 每条任务间隔秒数（默认 2）
            timeout: 整体超时秒数（默认 300）

        Returns:
            {"success": True, "total": N, "success_count": M, "fail_count": K, "results": [...]}
        """
        url = f"{self.base_url}/api/open/pixel/batch_authorize"

        payload = {
            "tasks": tasks,
            "interval": interval,
        }
        if username:
            payload["username"] = username
        if device:
            payload["device"] = device

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=timeout
            )

            data = response.json()

            if data.get("success"):
                print(f"[Skill] 批量授权完成: 总计 {data.get('total')}, "
                      f"成功 {data.get('success_count')}, "
                      f"失败 {data.get('fail_count')}")
            else:
                print(f"[Skill] 批量授权失败: {data.get('message')}")

            return data

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": f"批量授权超时 ({timeout}s)",
                "total": len(tasks),
                "success_count": 0,
                "fail_count": len(tasks),
                "results": []
            }
        except Exception as e:
            print(f"[Skill] 批量授权异常: {e}")
            return {
                "success": False,
                "message": str(e),
                "total": len(tasks),
                "success_count": 0,
                "fail_count": len(tasks),
                "results": []
            }

    def authorize_from_file(
        self,
        file_path: str,
        username: Optional[str] = None,
        device: Optional[str] = None,
        interval: int = 2
    ) -> Dict[str, Any]:
        """从文本文件读取像素-BM对应关系并批量授权

        文件格式：每行一对，用逗号或空格分隔
        pixel_id1,target_bm_id1
        pixel_id2,target_bm_id2

        Args:
            file_path: 文本文件路径
            username: 指定用户名路由
            device: 指定设备 ID 前缀
            interval: 每条任务间隔秒数

        Returns:
            批量授权结果
        """
        tasks = self._parse_task_file(file_path)
        if not tasks:
            return {
                "success": False,
                "message": f"文件 {file_path} 中没有有效的任务数据",
                "total": 0,
                "success_count": 0,
                "fail_count": 0,
                "results": []
            }

        print(f"[Skill] 从文件读取到 {len(tasks)} 条任务")
        return self.batch_authorize(tasks, username=username, device=device, interval=interval)

    def _parse_task_file(self, file_path: str) -> List[Dict[str, str]]:
        """解析任务文件，返回 [{"pixel_id": "xxx", "target_account_id": "yyy"}, ...]"""
        tasks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    parts = None
                    for sep in [',', '\t', ' ', '|']:
                        if sep in line:
                            parts = [p.strip() for p in line.split(sep)]
                            break

                    if not parts or len(parts) < 2:
                        print(f"[Skill] 跳过第 {line_num} 行（格式错误）: {line}")
                        continue

                    pixel_id = parts[0]
                    target_bm_id = parts[1]

                    if pixel_id and target_bm_id:
                        tasks.append({
                            "pixel_id": pixel_id,
                            "target_account_id": target_bm_id,
                        })
        except FileNotFoundError:
            print(f"[Skill] 文件不存在: {file_path}")
        except Exception as e:
            print(f"[Skill] 读取文件失败: {e}")

        return tasks

    def _start_authorization(
        self,
        pixel_id: str,
        target_account_id: str,
        username: Optional[str],
        device: Optional[str]
    ) -> Optional[str]:
        url = f"{self.base_url}/api/open/pixel/authorize"

        payload = {
            "pixel_id": pixel_id,
            "target_account_id": target_account_id
        }

        if username:
            payload["username"] = username
        if device:
            payload["device"] = device

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=10
            )

            data = response.json()

            if data.get("success"):
                task_id = data.get("task_id")
                print(f"[Skill] 授权任务已下发: task_id={task_id}, device={data.get('device')}")
                return task_id
            else:
                print(f"[Skill] 发起授权失败: {data.get('message')}")
                return None

        except Exception as e:
            print(f"[Skill] 请求异常: {e}")
            return None

    def _poll_result(self, task_id: str, timeout: int) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/open/pixel/result/{task_id}"

        start_time = time.time()
        max_retries = timeout // 2

        for _ in range(max_retries):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    timeout=10
                )

                data = response.json()

                if not data.get("success"):
                    print(f"[Skill] 查询结果失败: {data.get('message')}")
                    return None

                status = data.get("status")

                if status == "done":
                    result = data.get("result")
                    print(f"[Skill] 任务完成: {result}")
                    return result
                elif status == "pending":
                    elapsed = time.time() - start_time
                    print(f"[Skill] 任务进行中... (已等待 {elapsed:.1f}s)")
                    time.sleep(2)
                else:
                    print(f"[Skill] 未知状态: {status}")
                    return None

            except Exception as e:
                print(f"[Skill] 查询异常: {e}")
                time.sleep(2)

        print(f"[Skill] 任务超时（{timeout}s）")
        return None

    def _format_result(
        self,
        pixel_id: str,
        target_account_id: str,
        result: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if result is None:
            return {
                "success": False,
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
                "authorized": False,
                "message": "任务超时或查询失败"
            }

        status = result.get("status")

        if status == "ok":
            return {
                "success": True,
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
                "authorized": True,
                "message": result.get("message", "像素授权成功")
            }
        else:
            return {
                "success": False,
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
                "authorized": False,
                "message": result.get("message", "授权失败")
            }

    def get_online_devices(self) -> Dict[str, Any]:
        url = f"{self.base_url}/api/open/pixel/devices"

        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=10
            )

            data = response.json()

            if data.get("success"):
                return data.get("data", {})
            else:
                print(f"[Skill] 获取设备列表失败: {data.get('message')}")
                return {}

        except Exception as e:
            print(f"[Skill] 请求异常: {e}")
            return {}


def main():
    api_key = os.getenv("FBSPIDER_API_KEY", "fbk_xxxxx")
    base_url = os.getenv("FBSPIDER_BASE_URL", "http://47.129.247.139:7150")
    skill = FbspiderPixelAuthorize(api_key, base_url)

    # === 示例 1: 单次授权 ===
    print("=== 单次授权示例 ===")
    devices = skill.get_online_devices()
    print(f"在线设备: {devices}")

    result = skill.authorize(
        pixel_id="123456789",
        target_account_id="987654321",
        username="liaoyu354@gmail.com",
        timeout=60
    )
    print(f"授权结果: {result}")

    # === 示例 2: 批量授权 ===
    print("\n=== 批量授权示例 ===")
    tasks = [
        {"pixel_id": "111111111", "target_account_id": "222222222"},
        {"pixel_id": "333333333", "target_account_id": "444444444"},
    ]
    batch_result = skill.batch_authorize(tasks, username="liaoyu354@gmail.com", interval=2)
    print(f"批量结果: 成功 {batch_result.get('success_count')}/{batch_result.get('total')}")

    # === 示例 3: 从文件批量授权 ===
    print("\n=== 文件批量授权示例 ===")
    # 先创建示例文件
    sample_file = "pixel_tasks_example.txt"
    with open(sample_file, 'w', encoding='utf-8') as f:
        f.write("# 像素ID,目标BM ID\n")
        f.write("111111111,222222222\n")
        f.write("333333333,444444444\n")

    file_result = skill.authorize_from_file(sample_file, username="liaoyu354@gmail.com")
    print(f"文件授权结果: {file_result}")

    if result["success"]:
        print("像素授权成功")
    else:
        print(f"像素授权失败: {result['message']}")


if __name__ == "__main__":
    main()
