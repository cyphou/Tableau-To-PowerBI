let
    // TODO: Configure the data source for connector type: textscan
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"diagnosis_code", "diagnosis_description", "diagnosis_category", "drg_code", "drg_weight", "expected_los_days", "cms_reimbursement"},
            {
                {"Sample 1", "Sample 2", "Sample 3", "Sample 4", 5, 6, 7},
                {"Sample 2", "Sample 3", "Sample 4", "Sample 5", 6, 7, 8}
            }
        )
    otherwise
        #table({"diagnosis_code", "diagnosis_description", "diagnosis_category", "drg_code", "drg_weight", "expected_los_days", "cms_reimbursement"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "primary_diagnosis_code", Admissions_+_Procedures, "diagnosis_code", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"admission_id", "patient_id", "admit_date", "discharge_date", "department", "attending_physician", "primary_diagnosis_code", "admission_type", "insurance_type", "bed_type", "discharge_disposition"}),
    #"Added LOS_Days" = Table.AddColumn(#"Expanded Joined", "LOS_Days", each DATEDIFF('day', [admit_date], [discharge_date])),
    #"Added LOS_Variance" = Table.AddColumn(#"Added LOS_Days", "LOS_Variance", each [LOS_Days] - [expected_los_days]),
    #"Added LOS_Status" = Table.AddColumn(#"Added LOS_Variance", "LOS_Status", each if [LOS_Variance] <= -1 then 'Below Expected' else if [LOS_Variance] <= 1 then 'On Track' else 'Extended' ),
    #"Added TotalCost" = Table.AddColumn(#"Added LOS_Status", "TotalCost", each [cost] + ([LOS_Days] * 2500)),
    #"Added CostVariance" = Table.AddColumn(#"Added TotalCost", "CostVariance", each [TotalCost] - [cms_reimbursement]),
    #"Added Profitable" = Table.AddColumn(#"Added CostVariance", "Profitable", each if [CostVariance] <= 0 then 'Yes' else 'No' ),
    #"Added CaseMixIndex" = Table.AddColumn(#"Added Profitable", "CaseMixIndex", each [drg_weight]),
    #"Added Readmission30" = Table.AddColumn(#"Added CaseMixIndex", "Readmission30", each if [discharge_disposition] = 'Readmitted' and [LOS_Days] < 30 then 1 else 0 ),
    #"Added AdmitHour" = Table.AddColumn(#"Added Readmission30", "AdmitHour", each DATEPART('hour', [admit_date])),
    #"Added AdmitDayOfWeek" = Table.AddColumn(#"Added AdmitHour", "AdmitDayOfWeek", each DATENAME('weekday', [admit_date])),
    #"Renamed Columns" = Table.RenameColumns(#"Added AdmitDayOfWeek", {{"admission_id", "AdmissionID"}, {"patient_id", "PatientID"}}),
    Result = #"Renamed Columns"
in
    Result