let
    // Source SQL Server
    Source = try

        let

            _src = Sql.Database("localhost", "HRDatabase"),

            _nav = _src{[Schema="dbo", Item="Employees"]}[Data]

        in _nav

    otherwise

        #table({"EmployeeID", "FirstName", "LastName", "HireDate", "Department", "JobTitle", "Salary", "Location", "Age", "YearsOfService", "PerformanceRating"}, {}),
    #"Added Tenure Category" = Table.AddColumn(_nav, "Tenure Category", each if [YearsOfService] < 2 then "New" else if [YearsOfService] < 5 then "Mid" else "Senior", type text),
    Result = #"Added Tenure Category"
in
    Result