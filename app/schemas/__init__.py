from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserOut
from app.schemas.course import CourseOut, SectionOut, CourseCreate, SectionCreate
from app.schemas.attendance import SessionCreate, SessionOut, QRResponse, ScanAttendanceRequest, AttendanceRecordOut
from app.schemas.assignment import (
    AssignmentCreate,
    AssignmentUpdate,
    AssignmentOut,
    BatchSubmissionItem,
    BatchSubmissionsRequest,
    BatchSubmissionResult,
    BatchSubmissionsResponse,
    SubmissionGradeRequest,
    SubmissionOut,
)
from app.schemas.student import StudentProfileOut, StudentAttendanceOut, StudentSubmissionOut
from app.schemas.verify import FolioVerificationOut, LinkDeviceRequest, DeviceOut

