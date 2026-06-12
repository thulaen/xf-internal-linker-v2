# apps.platform has no Django models.
#
# This file exists so that "from apps.platform import models" and
# "import apps.platform.models" succeed instead of raising
# ModuleNotFoundError (GlitchTip #23024).  Add real models here when
# the platform module grows a data layer.
