import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    async initServerData() {
        await super.initServerData();
        const [counties, districts] = await Promise.all([
            this.data.orm.searchRead("res.country.county", [], ["name", "code", "state_id"]),
            this.data.orm.searchRead("res.country.district", [], ["name", "code", "county_id"]),
        ]);
        this.county = counties;
        this.district = districts;
    },
});
