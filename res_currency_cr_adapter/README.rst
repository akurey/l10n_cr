.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

===========================
Costa Rica - Exchange Rates
===========================

The reference exchange rates of the Banco Central de Costa Rica (BCCR), selling and buying, loaded
automatically for companies that keep their accounts in colones or in dollars, and shown in the format
used in Costa Rica.

**Table of contents**

.. contents::
   :local:

Features
========

Automatic update
~~~~~~~~~~~~~~~~

* The BCCR's selling and buying rates of the dollar, from its Indicadores Económicos web service. A
  colón company gets the dollar's rates and a dollar company the colón's.
* The update runs every hour and only loads what is missing. Tomorrow's rate, which the BCCR publishes
  around 17:30, is loaded from 18:00 Costa Rica time, before the first documents of its day. A failed
  or late update is retried the next hour, and missed days are caught up.
* It is switched on per company. Branches use the rates of their root company. The BCCR token is shared
  by all companies.
* *Update Now* loads the missing rates right away, and *Load Past Rates* loads a period up to today,
  optionally replacing the rates entered manually.

Status
~~~~~~

In Settings and on the rated currency: whether the rates are up to date, tomorrow's is pending or
today's is missing, the date they are loaded through, and when the last update ran, whether it failed,
and when the next one runs. On the currency it is shown to accounting administrators, who can also
update and load past rates from there.

Costa Rica rate format
~~~~~~~~~~~~~~~~~~~~~~

For the currency the BCCR rates, on its form and in *Show Currency Rates*:

* Each rate is shown with the BCCR's date, the day it applies to documents. Odoo 20 converts with the
  last rate dated before the document (`odoo/odoo@cba671d <https://github.com/odoo/odoo/commit/cba671d>`_),
  so the module stores each rate the day before.
* The buying rate is shown and edited next to the selling one, as *Unit/Base* and *Base/Unit*.
* The source of each rate: the BCCR, or entered manually. A rate changed by hand becomes manual, and
  loads only overwrite it with *Replace Rates*. The rate list can be filtered by source.

Configuration
=============

In *Invoicing > Configuration > Settings*, under *Currencies*, with multi-currency on, for a company
whose fiscal country is Costa Rica and whose currency is the colón or the dollar:

#. Tick *BCCR Exchange Rates*.
#. Enter the *BCCR Token*. It is free: register on the BCCR's
   `Indicadores Económicos <https://sdd.bccr.fi.cr/es/IndicadoresEconomicos/Inicio/MiPerfil>`_ site and
   generate it from *Mi perfil*.

The rates load at the next hourly run, or right away with *Update Now*.

Upgrading from 19.0
===================

* The rates of the currency the BCCR rates move back a day, to the date Odoo 20 needs. Only companies
  whose fiscal country is Costa Rica are migrated.
* The buying rates and the token are kept.
* Companies that loaded their rates automatically keep the update on. Those that used Hacienda's rates
  now get the BCCR's, and need a token.
* The scheduled action runs every hour, and the settings Odoo 20 no longer uses are removed.

Credits
=======

Authors
~~~~~~~

* `AKUREY S.A. <https://www.akurey.com>`_

  * Carlos Wong <cwong@akurey.com>

Contributors
~~~~~~~~~~~~

* Carlos Wong (WhiteTiger008) <cewongq@gmail.com>
* Ran
* Esteban Monge
