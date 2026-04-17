let
    // TODO: Configure the data source for connector type: postgres
    // Replace the sample table below with the actual source expression.
    Source = try
        #table(
            {"admission_id", "patient_id", "admit_date", "discharge_date", "department", "attending_physician", "primary_diagnosis_code", "admission_type", "insurance_type", "bed_type", "discharge_disposition"},
            {
                {"Sample 1", "Sample 2", 3, 4, "Sample 5", "Sample 6", "Sample 7", "Sample 8", "Sample 9", "Sample 10", "Sample 11"},
                {"Sample 2", "Sample 3", 4, 5, "Sample 6", "Sample 7", "Sample 8", "Sample 9", "Sample 10", "Sample 11", "Sample 12"}
            }
        )
    otherwise
        #table({"admission_id", "patient_id", "admit_date", "discharge_date", "department", "attending_physician", "primary_diagnosis_code", "admission_type", "insurance_type", "bed_type", "discharge_disposition"}, {}),
    #"Joined Joined" = Table.NestedJoin(Source, "admission_id", Procedures, "admission_id", "Joined", JoinKind.LeftOuter),
    #"Expanded Joined" = Table.ExpandTableColumn(#"Joined Joined", "Joined", {"procedure_id", "procedure_code", "procedure_name", "procedure_date", "duration_minutes", "cost", "performing_physician"}),
    Result = #"Expanded Joined"
in
    Result