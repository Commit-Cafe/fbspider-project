import os
import time
import requests
from typing import Dict, Any, Optional, List


class FbspiderPixelAuthorize:

    ERROR_HINTS = {
        "没有在线设备": "请确认浏览器插件已安装并打开了 fbspider.com 页面",
        "没有匹配": "请确认指定设备 ID 正确，且浏览器插件页面已打开",
        "没有在线": "请确认浏览器插件页面已打开，插件已加载",
        "未登录 Facebook": "请先在浏览器中登录 business.facebook.com",
        "未登录": "请先在浏览器中登录 Facebook",
        "无法获取 fb_dtsg": "请先在浏览器中登录 business.facebook.com",
        "无法获取 Facebook 用户": "Facebook 登录状态失效，请刷新 business.facebook.com 页面",
        "缺少 businessID": "请在参数中指定 business_id（BM ID），或在浏览器中打开 BM 页面",
        "相同": "源 BM 和目标 BM 相同，无法分享给自己",
        "自己的业务编号": "源 BM 和目标 BM 相同，无法分享给自己",
        "权限不足": "当前 Facebook 账号可能没有该像素的分享权限",
        "无法分享": "该 BM 的像素可能受限，无法对外分享",
        "Unauthorized": "API Key 无效或已过期，请检查 X-API-Key",
        "Forbidden": "API Key 缺少必要权限 (device-control scope)",
        "ConnectionError": "后端服务未启动，请确认 fbspider-server 正在运行",
        "ConnectionRefusedError": "后端服务未启动，请确认 fbspider-server 正在运行",
        "未找到": "有可能是开了多个浏览器插件导致选错设备，建议只保留一个插件并关闭多余的",
    }

    def __init__(self, api_key: str, base_url: str = "http://47.129.247.139:7150"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
        }

    def _enrich_error(self, message: str) -> str:
        for key, hint in self.ERROR_HINTS.items():
            if key in message:
                return f"{message}（{hint}）"
        return message

    def _check_server_alive(self) -> Optional[str]:
        try:
            resp = requests.get(f"{self.base_url}/api/health", timeout=5)
            data = resp.json()
            if data.get("status") != "ok":
                mongo = data.get("checks", {}).get("mongo", "unknown")
                return f"服务状态异常: mongo={mongo}"
            online = data.get("checks", {}).get("online_devices", 0)
            if online == 0:
                return "服务正常但无在线设备，请确认浏览器插件已打开 fbspider.com 页面"
            return None
        except requests.exceptions.ConnectionError:
            return "无法连接后端服务，请确认 fbspider-server 正在运行（http://localhost:7150）"
        except Exception as e:
            return f"健康检查失败: {e}"

    def authorize(
        self,
        pixel_id: str,
        target_account_id: str,
        business_id: Optional[str] = None,
        username: Optional[str] = None,
        device: Optional[str] = None,
        timeout: int = 60
    ) -> Dict[str, Any]:
        task_id = self._start_authorization(
            pixel_id, target_account_id, business_id, username, device
        )

        if not task_id:
            error_msg = "发起授权任务失败"
            hint = self._check_server_alive()
            if hint:
                error_msg = f"{error_msg}。诊断: {hint}"
            return {
                "success": False,
                "pixel_id": pixel_id,
                "target_account_id": target_account_id,
                "authorized": False,
                "message": error_msg
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
            tasks: 列表，每项 {"pixel_id": "xxx", "target_account_id": "yyy", "business_id": "zzz"}
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

        文件格式：每行三个字段，用逗号或空格分隔
        源BM_ID,像素ID,目标BM_ID
        1281455183398723,965817239731745,1295757529414325
        1281455183398723,1639781780563928,1295757529414325

        也兼容旧格式（两列：像素ID,目标BM_ID）：
        pixel_id1,target_bm_id1

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

        # 分离跳过的任务
        skip_tasks = [t for t in tasks if t.get('_skip')]
        real_tasks = [t for t in tasks if not t.get('_skip')]

        result = self.batch_authorize(real_tasks, username=username, device=device, interval=interval)

        # 将跳过的任务加入结果
        if skip_tasks:
            skip_results = []
            for i, t in enumerate(skip_tasks):
                skip_results.append({
                    "index": len(result.get('results', [])) + i,
                    "pixel_id": t["pixel_id"],
                    "target_account_id": t["target_account_id"],
                    "success": False,
                    "authorized": False,
                    "message": t.get("_reason", "跳过：所属BM与目标BM相同"),
                })
            result['results'].extend(skip_results)
            result['total'] = len(tasks)
            result['fail_count'] = result.get('fail_count', 0) + len(skip_tasks)

        return result

    def _parse_task_file(self, file_path: str) -> List[Dict[str, str]]:
        """解析任务文件，返回 [{"pixel_id": "xxx", "target_account_id": "yyy", "business_id": "zzz"}, ...]
        
        支持格式：
        四列: 像素ID,所属BM,所有者,目标BM（取所属BM作为源BM）
        三列: 源BM,像素ID,目标BM
        两列: 像素ID,目标BM（兼容旧格式，不指定源BM）
        """
        tasks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    # 支持中文逗号和英文逗号
                    parts = None
                    for sep in ['，', ',', '\t', ' ', '|']:
                        if sep in line:
                            parts = [p.strip() for p in line.split(sep) if p.strip()]
                            break

                    if not parts or len(parts) < 2:
                        print(f"[Skill] 跳过第 {line_num} 行（格式错误）: {line}")
                        continue

                    # 过滤非数字部分（如中文描述）
                    numeric_parts = [p for p in parts if p.isdigit()]

                    if len(numeric_parts) >= 4:
                        # 四列: 像素ID,所属BM,所有者,目标BM → 取所属BM(第2列)作为源BM
                        pixel_id = numeric_parts[0]
                        business_id = numeric_parts[1]  # 所属BM
                        target_bm_id = numeric_parts[3]
                    elif len(numeric_parts) >= 3:
                        # 三列: 源BM,像素ID,目标BM
                        business_id = numeric_parts[0]
                        pixel_id = numeric_parts[1]
                        target_bm_id = numeric_parts[2]
                    elif len(numeric_parts) >= 2:
                        # 两列: 像素ID,目标BM（兼容旧格式）
                        pixel_id = numeric_parts[0]
                        target_bm_id = numeric_parts[1]
                        business_id = None
                    else:
                        print(f"[Skill] 跳过第 {line_num} 行（数字不足）: {line}")
                        continue

                    # 跳过源BM=目标BM的无效任务
                    if business_id and str(business_id) == str(target_bm_id):
                        print(f"[Skill] 跳过第 {line_num} 行（所属BM=目标BM，无法分享给自己）: {line}")
                        tasks.append({
                            "pixel_id": pixel_id,
                            "target_account_id": target_bm_id,
                            "_skip": True,
                            "_reason": "所属BM与目标BM相同，无法分享给自己"
                        })
                        continue

                    task = {
                        "pixel_id": pixel_id,
                        "target_account_id": target_bm_id,
                    }
                    if business_id:
                        task["business_id"] = business_id
                    tasks.append(task)
        except FileNotFoundError:
            print(f"[Skill] 文件不存在: {file_path}")
        except Exception as e:
            print(f"[Skill] 读取文件失败: {e}")

        return tasks

    def _start_authorization(
        self,
        pixel_id: str,
        target_account_id: str,
        business_id: Optional[str],
        username: Optional[str],
        device: Optional[str]
    ) -> Optional[str]:
        url = f"{self.base_url}/api/open/pixel/authorize"

        payload = {
            "pixel_id": pixel_id,
            "target_account_id": target_account_id
        }

        if business_id:
            payload["business_id"] = business_id
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
                msg = self._enrich_error(data.get('message', '未知错误'))
                print(f"[Skill] 发起授权失败: {msg}")
                return None

        except requests.exceptions.ConnectionError:
            hint = self._check_server_alive()
            print(f"[Skill] 连接失败: {hint or '未知网络错误'}")
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

    def share_to_ad_account(
        self,
        pixel_id: str,
        target_account_ids: list,
        business_id: Optional[str] = None,
        pixel_name: Optional[str] = None,
        pixel_asset_id: Optional[str] = None,
        username: Optional[str] = None,
        device: Optional[str] = None,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """像素分享给广告账户

        Args:
            pixel_id: 像素 ID（fbspider 显示的 Dataset ID，会自动搜索真实 asset ID）
            target_account_ids: 广告账户 ID 列表
            business_id: BM ID（可选，自动检测）
            pixel_name: 像素名称，用于搜索真实 asset ID（可选）
            pixel_asset_id: Facebook 真实 asset ID，跳过搜索直接使用（可选）
            username: 指定用户名路由
            device: 指定设备 ID 前缀
            timeout: 超时秒数

        Returns:
            {"success": bool, "pixel_id": str, "authorized": bool, "message": str}
        """
        task_id = self._start_share_to_ad_account(
            pixel_id, target_account_ids, business_id,
            pixel_name, pixel_asset_id,
            username, device
        )

        if not task_id:
            return {
                "success": False,
                "pixel_id": pixel_id,
                "target_account_ids": target_account_ids,
                "authorized": False,
                "message": "发起分享任务失败"
            }

        result = self._poll_result(task_id, timeout)
        return self._format_ad_account_result(pixel_id, target_account_ids, result)

    def batch_share_to_ad_account(
        self,
        tasks: List[Dict[str, Any]],
        username: Optional[str] = None,
        device: Optional[str] = None,
        interval: int = 2,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """批量像素分享给广告账户

        Args:
            tasks: 列表，每项 {"pixel_id": "xxx", "target_account_ids": ["yyy"], "business_id": "zzz"}
                   也兼容 {"pixel_id": "xxx", "target_account_id": "yyy"}
            username: 指定用户名路由
            device: 指定设备 ID 前缀
            interval: 每条任务间隔秒数
            timeout: 整体超时秒数

        Returns:
            {"success": True, "total": N, "success_count": M, "fail_count": K, "results": [...]}
        """
        url = f"{self.base_url}/api/open/pixel/batch_share_to_ad_account"

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
                print(f"[Skill] 批量分享给广告账户完成: 总计 {data.get('total')}, "
                      f"成功 {data.get('success_count')}, "
                      f"失败 {data.get('fail_count')}")
            else:
                print(f"[Skill] 批量分享给广告账户失败: {data.get('message')}")

            return data

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": f"批量分享超时 ({timeout}s)",
                "total": len(tasks),
                "success_count": 0,
                "fail_count": len(tasks),
                "results": []
            }
        except Exception as e:
            print(f"[Skill] 批量分享给广告账户异常: {e}")
            return {
                "success": False,
                "message": str(e),
                "total": len(tasks),
                "success_count": 0,
                "fail_count": len(tasks),
                "results": []
            }

    def share_to_ad_account_from_file(
        self,
        file_path: str,
        username: Optional[str] = None,
        device: Optional[str] = None,
        interval: int = 2
    ) -> Dict[str, Any]:
        """从文本文件读取像素-广告账户对应关系并批量分享

        文件格式：每行用逗号或空格分隔
        像素ID,广告账户ID1,广告账户ID2,...
        像素ID,BM_ID,广告账户ID1,广告账户ID2,...

        也兼容单账户:
        像素ID,广告账户ID

        Args:
            file_path: 文本文件路径
            username: 指定用户名路由
            device: 指定设备 ID 前缀
            interval: 每条任务间隔秒数

        Returns:
            批量分享结果
        """
        tasks = self._parse_ad_account_file(file_path)
        if not tasks:
            return {
                "success": False,
                "message": f"文件 {file_path} 中没有有效的任务数据",
                "total": 0,
                "success_count": 0,
                "fail_count": 0,
                "results": []
            }

        print(f"[Skill] 从文件读取到 {len(tasks)} 条广告账户分享任务")
        return self.batch_share_to_ad_account(tasks, username=username, device=device, interval=interval)

    def _start_share_to_ad_account(
        self,
        pixel_id: str,
        target_account_ids: list,
        business_id: Optional[str],
        pixel_name: Optional[str],
        pixel_asset_id: Optional[str],
        username: Optional[str],
        device: Optional[str]
    ) -> Optional[str]:
        url = f"{self.base_url}/api/open/pixel/share_to_ad_account"

        payload = {
            "pixel_id": pixel_id,
            "target_account_ids": target_account_ids,
        }
        if business_id:
            payload["business_id"] = business_id
        if pixel_name:
            payload["pixel_name"] = pixel_name
        if pixel_asset_id:
            payload["pixel_asset_id"] = pixel_asset_id
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
                print(f"[Skill] 广告账户分享任务已下发: task_id={task_id}, device={data.get('device')}")
                return task_id
            else:
                print(f"[Skill] 发起广告账户分享失败: {data.get('message')}")
                return None

        except Exception as e:
            print(f"[Skill] 请求异常: {e}")
            return None

    def _format_ad_account_result(
        self,
        pixel_id: str,
        target_account_ids: list,
        result: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if result is None:
            return {
                "success": False,
                "pixel_id": pixel_id,
                "target_account_ids": target_account_ids,
                "authorized": False,
                "message": "任务超时或查询失败"
            }

        status = result.get("status")

        if status == "ok":
            return {
                "success": True,
                "pixel_id": pixel_id,
                "target_account_ids": target_account_ids,
                "authorized": True,
                "message": result.get("message", "像素已成功分享给广告账户")
            }
        else:
            return {
                "success": False,
                "pixel_id": pixel_id,
                "target_account_ids": target_account_ids,
                "authorized": False,
                "message": result.get("message", "分享给广告账户失败")
            }

    def _parse_ad_account_file(self, file_path: str) -> List[Dict[str, Any]]:
        """解析广告账户分享任务文件

        支持格式：
        像素ID,广告账户ID                    → 单账户
        像素ID,广告账户ID1,广告账户ID2       → 多账户（同一像素分享给多个账户）
        像素ID,BM_ID,广告账户ID              → 指定 BM，三列时第2列为BM
        像素ID,BM_ID,广告账户ID1,广告账户ID2 → 指定 BM + 多账户
        """
        tasks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    parts = None
                    for sep in ['，', ',', '\t', ' ', '|']:
                        if sep in line:
                            parts = [p.strip() for p in line.split(sep) if p.strip()]
                            break

                    if not parts or len(parts) < 2:
                        print(f"[Skill] 跳过第 {line_num} 行（格式错误）: {line}")
                        continue

                    numeric_parts = [p for p in parts if p.isdigit()]

                    if len(numeric_parts) < 2:
                        print(f"[Skill] 跳过第 {line_num} 行（数字不足）: {line}")
                        continue

                    pixel_id = numeric_parts[0]

                    if len(numeric_parts) == 2:
                        # 两列: 像素ID,广告账户ID
                        task = {
                            "pixel_id": pixel_id,
                            "target_account_id": numeric_parts[1],
                        }
                    else:
                        # 三列及以上: 像素ID,BM_ID,广告账户ID1[,广告账户ID2,...]
                        business_id = numeric_parts[1]
                        account_ids = numeric_parts[2:]
                        task = {
                            "pixel_id": pixel_id,
                            "business_id": business_id,
                        }
                        if len(account_ids) == 1:
                            task["target_account_id"] = account_ids[0]
                        else:
                            task["target_account_ids"] = account_ids

                    tasks.append(task)
        except FileNotFoundError:
            print(f"[Skill] 文件不存在: {file_path}")
        except Exception as e:
            print(f"[Skill] 读取文件失败: {e}")

        return tasks

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
        business_id="111222333",
        username="liaoyu354@gmail.com",
        timeout=60
    )
    print(f"授权结果: {result}")

    # === 示例 2: 批量授权 ===
    print("\n=== 批量授权示例 ===")
    tasks = [
        {"pixel_id": "111111111", "target_account_id": "222222222", "business_id": "333333333"},
        {"pixel_id": "444444444", "target_account_id": "555555555", "business_id": "666666666"},
    ]
    batch_result = skill.batch_authorize(tasks, username="liaoyu354@gmail.com", interval=2)
    print(f"批量结果: 成功 {batch_result.get('success_count')}/{batch_result.get('total')}")

    # === 示例 3: 从文件批量授权 ===
    print("\n=== 文件批量授权示例 ===")
    # 先创建示例文件
    sample_file = "pixel_tasks_example.txt"
    with open(sample_file, 'w', encoding='utf-8') as f:
        f.write("# 源BM_ID,像素ID,目标BM_ID\n")
        f.write("333333333,111111111,222222222\n")
        f.write("666666666,444444444,555555555\n")

    file_result = skill.authorize_from_file(sample_file, username="liaoyu354@gmail.com")
    print(f"文件授权结果: {file_result}")

    if result["success"]:
        print("像素授权成功")
    else:
        print(f"像素授权失败: {result['message']}")


if __name__ == "__main__":
    main()
