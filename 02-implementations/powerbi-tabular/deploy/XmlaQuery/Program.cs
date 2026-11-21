// XmlaQuery: execute one DAX query file against a Power BI semantic model through the XMLA endpoint.
// Connection string (service principal form documented for Power BI XMLA):
//   Data Source=powerbi://api.powerbi.com/v1.0/myorg/<workspace>;Initial Catalog=<model>;User ID=app:<appId>@<tenantId>;Password=<secret>
// It is read from SLC_XMLA_CONNECTION_STRING so the secret never appears on a command line.
using System.Globalization;
using System.Text.Json;
using Microsoft.AnalysisServices.AdomdClient;

if (args.Length != 1)
{
    Console.Error.WriteLine("usage: XmlaQuery <query.dax>");
    return 2;
}

var connectionString = Environment.GetEnvironmentVariable("SLC_XMLA_CONNECTION_STRING");
if (string.IsNullOrWhiteSpace(connectionString))
{
    Console.Error.WriteLine("SLC_XMLA_CONNECTION_STRING is not set");
    return 2;
}

var dax = File.ReadAllText(args[0]);
using var connection = new AdomdConnection(connectionString);
connection.Open();
using var command = new AdomdCommand(dax, connection);
using var reader = command.ExecuteReader();

var columns = new string[reader.FieldCount];
for (var i = 0; i < reader.FieldCount; i++)
{
    columns[i] = reader.GetName(i);
}

var rows = new List<object?[]>();
while (reader.Read())
{
    var row = new object?[reader.FieldCount];
    for (var i = 0; i < reader.FieldCount; i++)
    {
        row[i] = reader.IsDBNull(i) ? null : reader.GetValue(i) switch
        {
            DateTime d => d.ToString("yyyy-MM-dd'T'HH:mm:ss", CultureInfo.InvariantCulture),
            var v => v,
        };
    }
    rows.Add(row);
}

Console.Out.Write(JsonSerializer.Serialize(new { columns, rows }));
return 0;
