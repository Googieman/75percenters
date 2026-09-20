const PORTAL_PAGE_URLS = new Set([
  "https://sp.srmist.edu.in/srmiststudentportal/students/template/HRDSystem.jsp",
  "https://sp.srmist.edu.in/srmiststudentportal/students/report/studentAttendanceDetails.jsp",
]);

export function isAllowedPortalUrl(url) {
  return typeof url === "string" && PORTAL_PAGE_URLS.has(url);
}
