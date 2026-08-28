/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ZkDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            data: {
                device_count: 0,
                online_device_count: 0,
                offline_device_count: 0,
                log_count: 0,
                today_log_count: 0,
                unprocessed_log_count: 0,
                error_log_count: 0,
                last_punch_time: "",
                devices: [],
                recent_logs: [],
            }
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.data = await this.orm.call("zk.attendance.dashboard", "get_dashboard_data", []);
    }

    openAction(xmlId, context = {}) {
        this.action.doAction(xmlId, { additionalContext: context });
    }
}

ZkDashboard.template = "smr_zk_attendace.Dashboard";
registry.category("actions").add("smr_zk_attendace.dashboard", ZkDashboard);
