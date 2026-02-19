"""BigTime API client for fetching projects and time budgets."""

import time
import requests
from config import BigTimeConfig


class BigTimeClient:
    """Client for the BigTime REST API v2."""

    def __init__(self):
        self.base_url = BigTimeConfig.BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._authenticated = False

    def authenticate(self):
        """Authenticate using firm API token or user credentials."""
        if BigTimeConfig.API_TOKEN and BigTimeConfig.FIRM_ID:
            self._auth_with_firm_token()
        elif BigTimeConfig.USERNAME and BigTimeConfig.PASSWORD:
            self._auth_with_credentials()
        else:
            raise ValueError(
                "No BigTime credentials configured. "
                "Set BIGTIME_API_TOKEN + BIGTIME_FIRM_ID, "
                "or BIGTIME_USERNAME + BIGTIME_PASSWORD in .env"
            )
        self._authenticated = True

    def _auth_with_firm_token(self):
        """Authenticate with a permanent firm-level API token."""
        resp = self._request("POST", "/session/firm")
        self.session.headers.update({
            "X-Auth-ApiToken": BigTimeConfig.API_TOKEN,
            "X-Auth-Realm": BigTimeConfig.FIRM_ID,
        })

    def _auth_with_credentials(self):
        """Authenticate with username/password to get a session token."""
        resp = self._request("POST", "/session", json={
            "UserId": BigTimeConfig.USERNAME,
            "Pwd": BigTimeConfig.PASSWORD,
        })
        data = resp.json()
        self.session.headers.update({
            "X-Auth-Token": data["token"],
            "X-Auth-Realm": str(data["firm"]),
        })

    def _request(self, method, path, **kwargs):
        """Make an API request with rate-limit retry handling."""
        url = f"{self.base_url}{path}"
        for attempt in range(4):
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code == 503:
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def get_active_projects(self):
        """Fetch all active projects.

        Returns list of dicts with project info including SystemId, Nm,
        ProjectCode, ClientId, StartDt, EndDt, etc.
        """
        resp = self._request("GET", "/project")
        return resp.json()

    def get_project_detail(self, project_sid):
        """Fetch detailed info for a single project."""
        resp = self._request("GET", f"/project/detail/{project_sid}?View=Detailed")
        return resp.json()

    def get_budget_status(self, project_sid):
        """Fetch budget status (actuals) by project.

        Returns per-task totals: HoursInput, HoursBill, FeesInput,
        FeesCost, ExpensesInput, ExpensesBillable, TotalWip.
        """
        resp = self._request("GET", f"/task/BudgetStatusByProject/{project_sid}")
        return resp.json()

    def get_project_tasks(self, project_sid, show_completed=False):
        """Fetch tasks for a project, including budget fields."""
        param = "True" if show_completed else "False"
        resp = self._request(
            "GET", f"/task/listByProject/{project_sid}?showCompleted={param}"
        )
        return resp.json()

    def get_task_detail(self, task_sid):
        """Fetch detailed task info including BudgetHours, BudgetFees, etc."""
        resp = self._request("GET", f"/task/detail/{task_sid}?View=Detailed")
        return resp.json()

    def get_project_budgets(self, project_sid):
        """Fetch tasks with their budgets and actuals for a project.

        Returns a list of dicts combining task info with budget status.
        """
        tasks = self.get_project_tasks(project_sid)
        budget_status = self.get_budget_status(project_sid)

        # Index budget status by TaskSid for quick lookup
        budget_by_task = {}
        if isinstance(budget_status, list):
            for entry in budget_status:
                budget_by_task[entry.get("TaskSid")] = entry

        results = []
        for task in tasks if isinstance(tasks, list) else []:
            task_sid = task.get("TaskSid") or task.get("Id")
            budget = budget_by_task.get(task_sid, {})
            results.append({
                "TaskSid": task_sid,
                "TaskName": task.get("Nm", task.get("TaskNm", "")),
                "BudgetHours": task.get("BudgetHrs", task.get("BudgetHours", 0)) or 0,
                "BudgetFees": task.get("BudgetFees", 0) or 0,
                "HoursLogged": budget.get("HoursInput", 0) or 0,
                "HoursBillable": budget.get("HoursBill", 0) or 0,
                "FeesActual": budget.get("FeesInput", 0) or 0,
                "PercentComplete": task.get("PerComp", 0) or 0,
            })
        return results

    def get_all_project_summaries(self):
        """Fetch all active projects with their aggregated budget summaries.

        Returns a list of dicts: one per project with total budget hours,
        hours logged, and remaining hours.
        """
        projects = self.get_active_projects()
        summaries = []

        for proj in projects if isinstance(projects, list) else []:
            sid = proj.get("SystemId") or proj.get("Id")
            if not sid:
                continue

            try:
                budgets = self.get_project_budgets(sid)
            except requests.HTTPError:
                budgets = []

            total_budget = sum(b["BudgetHours"] for b in budgets)
            total_logged = sum(b["HoursLogged"] for b in budgets)
            total_remaining = total_budget - total_logged

            summaries.append({
                "ProjectSid": sid,
                "ProjectName": proj.get("Nm", proj.get("Name", "")),
                "ProjectCode": proj.get("ProjectCode", ""),
                "StartDate": proj.get("StartDt", ""),
                "EndDate": proj.get("EndDt", ""),
                "BudgetHours": total_budget,
                "HoursLogged": total_logged,
                "HoursRemaining": total_remaining,
                "Tasks": budgets,
            })

        return summaries
