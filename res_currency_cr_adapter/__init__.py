# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from . import models
from . import tools


def uninstall_hook(env):
    # Bring back Odoo's "Show Currency Rates", which the module replaces in the currency's actions menu
    env.ref('base.act_view_currency_rates').binding_model_id = env.ref('base.model_res_currency')
