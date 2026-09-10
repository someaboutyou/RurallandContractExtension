"""Survey service package - split from monolithic survey_service.py.

Each submodule defines a mixin class.  SurveyService inherits from all of
them so every method is available via ``self`` as before.  The singleton
``survey_service`` is re-exported so existing
``from app.services.survey_service import survey_service`` still works.
"""

from app.services.survey.base import SurveyServiceBase
from app.services.survey.batch import SurveyServiceBatchMixin
from app.services.survey.task import SurveyServiceTaskMixin
from app.services.survey.issuer import SurveyServiceIssuerMixin
from app.services.survey.result import SurveyServiceResultMixin
from app.services.survey.changes import SurveyServiceChangesMixin
from app.services.survey.tags import SurveyServiceTagsMixin
from app.services.survey.restructure import SurveyServiceRestructureMixin
from app.services.survey.authorization import SurveyServiceAuthorizationMixin
from app.services.survey.attachments import SurveyServiceAttachmentsMixin
from app.services.survey.exports import SurveyServiceExportsMixin
from app.services.survey.parcel_ops import SurveyServiceParcelOpsMixin
from app.services.survey.parcel_geometry import SurveyServiceParcelGeometryMixin
from app.services.survey.household import SurveyServiceHouseholdMixin


class SurveyService(
    SurveyServiceBase,
    SurveyServiceBatchMixin,
    SurveyServiceTaskMixin,
    SurveyServiceIssuerMixin,
    SurveyServiceResultMixin,
    SurveyServiceChangesMixin,
    SurveyServiceTagsMixin,
    SurveyServiceRestructureMixin,
    SurveyServiceAuthorizationMixin,
    SurveyServiceAttachmentsMixin,
    SurveyServiceExportsMixin,
    SurveyServiceParcelOpsMixin,
    SurveyServiceParcelGeometryMixin,
    SurveyServiceHouseholdMixin,
):
    """Composed survey service - all methods from submodules."""
    pass


survey_service = SurveyService()
